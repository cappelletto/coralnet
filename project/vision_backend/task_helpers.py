"""
This file contains helper functions to vision_backend.tasks.
"""
import abc
from collections import Counter, defaultdict
from logging import getLogger
import re

import numpy as np
from django.conf import settings
from django.core.mail import mail_admins
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from spacer.data_classes import ImageLabels
from spacer.messages import (
    ClassifyImageMsg,
    ClassifyReturnMsg,
    ExtractFeaturesMsg,
    JobReturnMsg,
    TrainClassifierMsg,
)

from accounts.utils import get_robot_user
from annotations.models import Annotation
from api_core.models import ApiJob, ApiJobUnit
from errorlogs.utils import instantiate_error_log
from images.models import Image, Point
from jobs.exceptions import JobError
from jobs.models import Job
from jobs.utils import finish_jobs
from labels.models import Label
from .exceptions import RowColumnMismatchError
from .models import Classifier, ClassifyImageEvent, Features, Score
from .utils import (
    extractor_to_name,
    reset_invalid_features_bulk,
    schedule_source_check,
    source_is_finished_with_core_jobs,
)

logger = getLogger(__name__)


# This function is generally called outside of Django views, meaning the
# middleware which does atomic transactions isn't active. So we use this
# decorator to get that property.
@transaction.atomic
def add_annotations(image_id: int,
                    res: ClassifyReturnMsg,
                    label_objs: list[Label],
                    classifier: Classifier) -> str:
    """
    Adds DB Annotations using the scores in the spacer return message.

    :param image_id: Database ID of the Image to add scores for.
    :param res: ClassifyReturnMsg from spacer.
    :param label_objs: Iterable of Label DB objects, one per label in the
      source's labelset.
    :param classifier: Classifier that will get attribution for the changes.

    May throw an IntegrityError when trying to save annotations. The caller is
    responsible for handling the error. In this error case, no annotations
    are saved due to the @transaction.atomic decorator.
    """
    img = Image.objects.get(pk=image_id)
    points = Point.objects.filter(image=img).order_by('id')
    event_details = dict()

    create_all = not img.annotation_set.exists()
    create_all_list = []

    # From spacer 0.2 we store row, col locations in features and in
    # classifier scores. This allows us to match scores to points
    # based on (row, col) locations. If not, we have to rely on
    # the points always being ordered as order_by('id').
    for itt, point in enumerate(points):
        if res.valid_rowcol:
            # Retrieve score vector for (row, column) location
            try:
                scores = res[(point.row, point.column)]
            except KeyError:
                raise RowColumnMismatchError
        else:
            try:
                _, _, scores = res.scores[itt]
            except IndexError:
                raise RowColumnMismatchError
        label = label_objs[int(np.argmax(scores))]

        if create_all:
            # Gather annotations to be saved more speedily in bulk. We
            # only bother with this for the common case where all of them
            # are new. Outside of that common case, it's typically just a
            # few annotations being changed.
            create_all_list.append(Annotation(
                point=point,
                image=img,
                source=img.source,
                label=label,
                user=get_robot_user(),
                robot_version=classifier,
            ))
            result = Annotation.objects.UpdateResultsCodes.ADDED.value
        else:
            # Individual annotation create/update.
            result = Annotation.objects.update_point_annotation_if_applicable(
                point=point,
                label=label,
                now_confirmed=False,
                user_or_robot_version=classifier)

        if result is not None:
            event_details[point.point_number] = dict(
                label=label.pk, result=result)
        # If None, then we decided it's better to not include the point in
        # the event details at all; e.g. it's a confirmed point that shouldn't
        # be overwritten by unconfirmed.
        # TODO: CoralNet 1.15 changed the semantics here; this case used to be
        #  reported as 'no change'. At some point, a data migration should be
        #  written to migrate pre-1.15 ClassifyImageEvents to use the new
        #  semantics.
        #  This may be difficult, involving cross-referencing reversion entries
        #  to see if the point was already confirmed at this time, or to see
        #  if the 'no change' entry actually disagreed with a previous entry.
        #  There is no rush to do this until the details of pre-1.15
        #  ClassifyImageEvents are displayed in any way, which will probably be
        #  done on the Annotation History page at some point.

    if create_all:
        Annotation.objects.bulk_create(create_all_list)

    event = ClassifyImageEvent(
        source_id=img.source_id,
        image_id=image_id,
        classifier_id=classifier.pk,
        details=event_details,
    )
    event.save()

    counter = Counter([d['result'] for d in event_details.values()])
    # Example: 2 annotations added, 3 changed, 5 not changed
    # sorted() puts added first, then changed, then not changed.
    summary_items = []
    for index, (result, count) in enumerate(sorted(counter.items())):
        if index == 0:
            summary_items.append(f"{count} annotations {result}")
        else:
            summary_items.append(f"{count} {result}")
    return ", ".join(summary_items)


def add_scores(image_id: int,
               res: ClassifyReturnMsg,
               label_objs: list[Label]):
    """
    Adds DB Scores using the scores in the spacer return message.

    :param image_id: Database ID of the Image to add scores for.
    :param res: ClassifyReturnMsg from spacer.
    :param label_objs: Iterable of Label DB objects, one per label in the
      source's labelset.
    """
    img = Image.objects.get(pk=image_id)

    # First, delete all scores associated with this image.
    Score.objects.filter(image=img).delete()

    # Figure out how many of the (top) scores to store.
    nbr_scores = min(settings.NBR_SCORES_PER_ANNOTATION, len(res.classes))

    # Now, go through and create new ones.
    points = Point.objects.filter(image=img).order_by('id')

    score_objs = []
    for itt, point in enumerate(points):
        if res.valid_rowcol:
            try:
                scores = res[(point.row, point.column)]
            except KeyError:
                raise RowColumnMismatchError
        else:
            try:
                _, _, scores = res.scores[itt]
            except IndexError:
                raise RowColumnMismatchError
        inds = np.argsort(scores)[::-1][:nbr_scores]
        for ind in inds:
            score_objs.append(
                Score(
                    source=img.source,
                    image=img,
                    label=label_objs[int(ind)],
                    point=point,
                    score=int(round(scores[ind]*100))
                )
            )
    Score.objects.bulk_create(score_objs)


def make_dataset(images: list[Image]) -> ImageLabels:
    """
    Helper function for classifier_submit.
    Assembles all features and ground truth annotations
    for training and evaluation of the robot classifier.
    """
    data = dict()
    for img in images:
        feature_key = img.features.data_loc.key
        anns = Annotation.objects.filter(image=img).\
            annotate(gt_label=F('label__id')).\
            annotate(row=F('point__row')). \
            annotate(col=F('point__column'))
        data[feature_key] = [
            (ann.row, ann.col, ann.gt_label) for ann in anns]
    return ImageLabels(data)


class SpacerResultHandler(abc.ABC):
    """
    Each type of collectable spacer job should define a subclass
    of this base class.
    """
    # This must match the corresponding Job's job_name AND the
    # spacer JobMsg's task_name (which are assumed to be the same).
    job_name = None

    # Error classes which are considered temporary or end-user errors,
    # rather than errors demanding attention of coralnet / pyspacer devs.
    non_priority_error_classes = []

    def handle_job_results(self, job_results: list[JobReturnMsg]):
        """
        The job_results must all have the same task name.
        """
        spacer_task_results = []

        for job_res in job_results:
            if not job_res.ok:
                spacer_error = self.handle_job_result_error(job_res)
            else:
                spacer_error = None

            # CoralNet currently only submits spacer jobs containing a single
            # task.
            task = job_res.original_job.tasks[0]
            spacer_task_results.append(dict(
                task=task,
                job_res=job_res,
                spacer_error=spacer_error,
            ))

        self.jobs_by_id = self.get_internal_jobs(
            [result['task'] for result in spacer_task_results])

        self.handle_spacer_task_results(spacer_task_results)

    @classmethod
    def handle_job_result_error(cls, job_res):
        # Spacer got an uncaught error.
        error_traceback = job_res.error_message
        # Last line of the traceback should serve as a decent
        # one-line summary. Has the error class and message.
        error_message = error_traceback.splitlines()[-1]
        # The error message should be either like:
        # 1) `somemodule.SomeError: some error info`.
        # We extract the error class/info as the part before/after
        # the first colon.
        # 2) `AssertionError`. Just a class, no colon, no detail.
        if ':' in error_message:
            error_class, error_info = error_message.split(':', maxsplit=1)
            error_info = error_info.strip()
        else:
            error_class = error_message
            error_info = ""

        if error_class not in cls.non_priority_error_classes:
            # Priority error; treat like an internal server error.

            job_res_repr = repr(job_res)
            if len(job_res_repr) > settings.EMAIL_SIZE_SOFT_LIMIT:
                job_res_repr = (
                    job_res_repr[:settings.EMAIL_SIZE_SOFT_LIMIT]
                    + " ...(truncated)"
                )

            mail_admins(
                f"Spacer job failed: {cls.job_name}",
                job_res_repr,
            )

            # Just the class name, not the whole dotted path.
            error_class_name = error_class.split('.')[-1]

            error_html = f'<pre>{error_traceback}</pre>'
            error_log = instantiate_error_log(
                kind=error_class_name,
                html=error_html,
                path=f"Spacer - {cls.job_name}",
                info=error_info,
                data=job_res_repr,
            )
            error_log.save()

        return error_class, error_message

    @staticmethod
    def get_internal_job_id(spacer_task):
        return int(spacer_task.job_token)

    @classmethod
    def get_internal_jobs(cls, spacer_tasks):
        job_ids = [cls.get_internal_job_id(task) for task in spacer_tasks]
        jobs_by_id = Job.objects.in_bulk(job_ids)
        return jobs_by_id

    @abc.abstractmethod
    def handle_spacer_task_results(self, spacer_task_results: list[dict]):
        raise NotImplementedError

    def handle_task_results_main_loop(self, spacer_task_results):
        finish_jobs_args = []

        for spacer_task_result in spacer_task_results:
            task = spacer_task_result['task']
            success = False
            result_message = None

            job_id = self.get_internal_job_id(task)
            try:
                job = self.jobs_by_id[job_id]
            except KeyError:
                # Job doesn't exist anymore. There shouldn't be anything
                # else to do regarding this result.
                continue

            try:
                result_message = self.handle_spacer_task_result(
                    **spacer_task_result)
                success = True
            except JobError as e:
                result_message = str(e)
            finally:
                finish_jobs_args.append(dict(
                    job=job,
                    success=success,
                    result_message=result_message,
                ))

        finish_jobs(finish_jobs_args)

    @classmethod
    def handle_spacer_task_result(cls, task, job_res, spacer_error):
        """
        Handles the result of a spacer task (a sub-unit within a spacer job)
        and raises a JobError if an error is found.
        Optionally returns a string result-message.
        """
        raise NotImplementedError


class SpacerFeatureResultHandler(SpacerResultHandler):
    job_name = 'extract_features'

    non_priority_error_classes = [
        # When this happens, it's probably a race condition that can be
        # recovered from in the next attempt.
        # But if it's not recoverable, then the Job should fail a few times
        # in a row and then issue a "failing repeatedly" notice to site
        # admins.
        'spacer.exceptions.RowColumnMismatchError',
    ]

    def handle_spacer_task_results(self, spacer_task_results: list[dict]):
        jobs = list(self.jobs_by_id.values())
        image_ids = [int(job.arg_identifier) for job in jobs]

        self.images_by_id = Image.objects.in_bulk(image_ids)
        self.features_by_image_id = Features.objects.in_bulk(
            image_ids, field_name='image_id')
        self.now = timezone.now()
        # TODO: Retrieving points and feature-extractor settings for all
        #  images in bulk here could result in more DB optimization.

        self.handle_task_results_main_loop(spacer_task_results)

        features = list(self.features_by_image_id.values())
        Features.objects.bulk_update(
            features,
            ['extracted', 'extractor', 'runtime_total',
             'extractor_loaded_remotely', 'extracted_date', 'has_rowcols'],
        )

        source_ids = set(job.source_id for job in jobs)
        for source_id in source_ids:
            if source_is_finished_with_core_jobs(source_id):
                # If not waiting for other 'core' jobs,
                # check if the source has any next steps.
                schedule_source_check(source_id)

    def handle_spacer_task_result(
            self,
            task: ExtractFeaturesMsg,
            job_res: JobReturnMsg,
            spacer_error: tuple[str, str] | None) -> None:

        internal_job = self.jobs_by_id[self.get_internal_job_id(task)]
        image_id = int(internal_job.arg_identifier)

        try:
            image = self.images_by_id[image_id]
        except KeyError:
            raise JobError(f"Image {image_id} doesn't exist anymore.")

        # This should always exist, so we'll let it be an uncaught
        # exception if it's missing.
        features = self.features_by_image_id[image_id]

        if spacer_error:
            # Error from spacer when running the spacer job.
            error_class, error_message = spacer_error
            raise JobError(error_message)

        # If there was no spacer error, then a task result is available.
        task_res = job_res.results[0]

        # Check that the row-col information hasn't changed.
        rowcols = [
            (p['row'], p['column']) for p
            in image.point_set.values('row', 'column')]
        if not set(rowcols) == set(task.rowcols):
            raise JobError(
                f"Row-col data for {image} has changed"
                f" since this task was submitted.")

        # Check that the active feature-extractor hasn't changed.
        task_extractor = extractor_to_name(task.extractor)
        if task_extractor != image.source.feature_extractor:
            raise JobError(
                f"Feature extractor selection has changed"
                f" since this task was submitted.")

        # If all is ok store meta-data.
        features.extracted = True
        features.extractor = task_extractor
        features.runtime_total = task_res.runtime

        features.extractor_loaded_remotely = \
            task_res.extractor_loaded_remotely
        features.extracted_date = self.now
        features.has_rowcols = True


class SpacerTrainResultHandler(SpacerResultHandler):
    job_name = 'train_classifier'

    non_priority_error_classes = [
        # This appears to be an uncommon race condition where points are
        # regenerated sometime during the gathering of training data.
        # We expect to automatically recover from this situation by
        # re-extracting features as necessary, and notifying admins
        # shouldn't be needed.
        'spacer.exceptions.RowColumnMismatchError',
    ]

    def handle_spacer_task_results(self, spacer_task_results: list[dict]):
        """
        This delegates almost everything to the main loop because we don't
        expect to batch many training jobs together, and thus bulk actions
        won't help much.
        """
        self.handle_task_results_main_loop(spacer_task_results)

        for job in self.jobs_by_id.values():
            # Successful jobs related to classifier history should persist
            # in the DB.
            if job.status == Job.Status.SUCCESS:
                job.persist = True
                job.save()

            if source_is_finished_with_core_jobs(job.source_id):
                # If not waiting for other 'core' jobs,
                # check if the source has any next steps.
                schedule_source_check(job.source_id)

    @classmethod
    def handle_spacer_task_result(
            cls,
            task: TrainClassifierMsg,
            job_res: JobReturnMsg,
            spacer_error: tuple[str, str] | None) -> str | None:

        # Parse out pk for current and previous classifiers.
        regex_pattern = (
            settings.ROBOT_MODEL_FILE_PATTERN
            # Replace the format placeholder with a number matcher
            .replace('{pk}', r'(\d+)')
            # Accept either forward or back slashes
            .replace('/', r'[/\\]')
            # Escape periods
            .replace('.', r'\.')
            # Only match at the end of the input string. The input will be
            # an absolute path, and the pattern will be a relative path.
            + '$'
        )
        model_filepath_regex = re.compile(regex_pattern)

        match = model_filepath_regex.search(task.model_loc.key)
        classifier_id = int(match.groups()[0])

        prev_classifier_ids = []
        for model_loc in task.previous_model_locs:
            match = model_filepath_regex.search(model_loc.key)
            prev_classifier_ids.append(int(match.groups()[0]))

        # Check that Classifier still exists.
        try:
            classifier = Classifier.objects.get(pk=classifier_id)
        except Classifier.DoesNotExist:
            raise JobError(
                f"Classifier {classifier_id} doesn't exist anymore.")

        if spacer_error:
            # Error from spacer when running the spacer job.
            classifier.status = Classifier.TRAIN_ERROR
            classifier.save()

            error_class, error_message = spacer_error
            if error_class == 'spacer.exceptions.RowColumnMismatchError':
                # Desynced rowcols.
                # Note that we could have checked for this before training
                # as well, but since checking takes a somewhat long time,
                # we try to only check when we have to (i.e. when a failure
                # actually happens).
                reset_invalid_features_bulk(
                    Image.objects.filter(source_id=classifier.source_id))

            raise JobError(error_message)

        # If there was no spacer error, then a task result is available.
        task_res = job_res.results[0]

        if len(prev_classifier_ids) != len(task_res.pc_accs):
            raise JobError(
                f"Number of previous classifiers doesn't match between"
                f" job ({len(prev_classifier_ids)})"
                f" and results ({len(task_res.pc_accs)}).")

        # Store generic stats
        classifier.runtime_train = task_res.runtime
        classifier.accuracy = task_res.acc
        classifier.epoch_ref_accuracy = str([int(round(10000 * ra)) for
                                             ra in task_res.ref_accs])
        classifier.save()

        # See whether we're accepting or rejecting the new classifier.
        if len(prev_classifier_ids) > 0:

            max_previous_acc = max(task_res.pc_accs)
            acc_threshold = \
                max_previous_acc * settings.NEW_CLASSIFIER_IMPROVEMENT_TH

            if acc_threshold > task_res.acc:
                # There are previous classifiers and the new one is not a
                # large enough improvement.
                # Abort without accepting the new classifier.
                #
                # This isn't really an error case; it just means we tried to
                # improve on the last classifier and we couldn't improve.

                classifier.status = Classifier.REJECTED_ACCURACY
                classifier.save()

                return (
                    f"Not accepted as the source's new classifier."
                    f" Highest accuracy among previous classifiers"
                    f" on the latest dataset: {max_previous_acc:.2f},"
                    f" threshold to accept new: {acc_threshold:.2f},"
                    f" accuracy from this training: {task_res.acc:.2f}")

        # We're accepting the new classifier.
        # Update accuracy for previous models.
        for pc_pk, pc_acc in zip(prev_classifier_ids, task_res.pc_accs):
            pc = Classifier.objects.get(pk=pc_pk)
            pc.accuracy = pc_acc
            pc.save()

        # Accept and save the current model
        classifier.status = Classifier.ACCEPTED
        classifier.save()

        # Set as the deployed classifier, if applicable
        source = classifier.source
        if source.trains_own_classifiers:
            source.deployed_classifier = classifier
            source.save()

        return f"New classifier accepted: {classifier.pk}"


class SpacerClassifyResultHandler(SpacerResultHandler):
    job_name = 'classify_image'

    non_priority_error_classes = [
        # If the user-specified URL has a non-image, then the Pillow load
        # step gets:
        # PIL.UnidentifiedImageError - cannot identify image file <...>
        'PIL.UnidentifiedImageError',
        # If the user specifies an image that's too big, then this error
        # class is raised.
        # This error class covers the point limit too, but that's already
        # checked by the deploy view.
        'spacer.exceptions.DataLimitError',
        # If the user specifies a point row or column that's not an
        # integer or is outside the image's valid range, then this
        # error class is raised.
        'spacer.exceptions.RowColumnInvalidError',
        # If there are any issues with downloading from the user-specified
        # URL, then the download step gets one of a few different
        # URLDownloadErrors. Now, this scenario could potentially indicate
        # a coralnet or pyspacer issue, but the common cases are either an
        # issue with the given URL's site, or just a random network error.
        'spacer.exceptions.URLDownloadError',
    ]

    @staticmethod
    def get_classifier_labelset(classifier_id):
        classifier = Classifier.objects.get(pk=classifier_id)
        labelset = classifier.source.labelset
        labels_values = list(labelset.locallabel_set.values(
            'global_label_id',
            'global_label__name',
            'code',
        ))
        return {
            label_values['global_label_id']: label_values
            for label_values in labels_values
        }

    def handle_spacer_task_results(self, spacer_task_results: list[dict]):
        job_ids = list(self.jobs_by_id.keys())
        self.job_units_by_job_id = ApiJobUnit.objects.in_bulk(
            job_ids, field_name='internal_job_id')
        self.labelsets_by_classifier = dict()

        self.handle_task_results_main_loop(spacer_task_results)

        job_units = list(self.job_units_by_job_id.values())
        ApiJobUnit.objects.bulk_update(job_units, ['result_json'])

        api_jobs = (
            ApiJob.objects
            .filter(apijobunit__in=[unit.pk for unit in job_units])
            .annotate(
                pending_units=Count(
                    'apijobunit',
                    filter=Q(
                        apijobunit__internal_job__status
                        =Job.Status.PENDING)),
                in_progress_units=Count(
                    'apijobunit',
                    filter=Q(
                        apijobunit__internal_job__status
                        =Job.Status.IN_PROGRESS)),
            )
        )
        api_jobs_to_update = []
        for api_job in api_jobs:
            if (
                api_job.pending_units == 0
                and api_job.in_progress_units == 0
                and not api_job.finish_date
            ):
                # All other units of the API job have finished too.
                api_job.finish_date = timezone.now()
                api_jobs_to_update.append(api_job)
        ApiJob.objects.bulk_update(api_jobs_to_update, ['finish_date'])

    def handle_spacer_task_result(
            self,
            task: ClassifyImageMsg,
            job_res: JobReturnMsg,
            spacer_error: tuple[str, str] | None) -> None:

        job_id = self.get_internal_job_id(task)

        try:
            job_unit = self.job_units_by_job_id[job_id]
        except KeyError:
            raise JobError(
                f"API job unit for internal-job {job_id}"
                f" does not exist.")

        if spacer_error:
            # Error from spacer when running the spacer job.
            error_class, error_message = spacer_error
            raise JobError(error_message)

        # If there was no spacer error, then a task result is available.
        task_res = job_res.results[0]

        classifier_id = job_unit.request_json['classifier_id']
        if classifier_id not in self.labelsets_by_classifier:
            try:
                self.labelsets_by_classifier[classifier_id] = (
                    self.get_classifier_labelset(classifier_id))
            except Classifier.DoesNotExist:
                raise JobError(
                    f"Classifier of id {classifier_id} does not exist.")

        job_unit.result_json = dict(
            url=job_unit.request_json['url'],
            points=self.build_points_dicts(
                task_res, self.labelsets_by_classifier[classifier_id]),
        )

    @staticmethod
    def build_points_dicts(
            res: ClassifyReturnMsg, labels: dict[int, dict]):
        """
        Converts scores from the deploy call to the dictionary returned
        by the API
        """

        # Figure out how many of the (top) scores to store.
        nbr_scores = min(settings.NBR_SCORES_PER_ANNOTATION,
                         len(res.classes))

        classes_info = [
            labels[global_label_id]
            for global_label_id in res.classes
        ]

        data = []
        for row, col, scores in res.scores:
            # Grab the indices of the highest-scoring labels.
            best_scoring_indices = np.argsort(scores)[::-1][:nbr_scores]
            classifications = []
            for ind in best_scoring_indices:
                class_info = classes_info[ind]
                classifications.append(dict(
                    label_id=class_info['global_label_id'],
                    label_name=class_info['global_label__name'],
                    label_code=class_info['code'],
                    score=scores[ind],
                ))
            data.append(dict(
                row=row, column=col, classifications=classifications,
            ))
        return data


handler_classes = [
    SpacerFeatureResultHandler,
    SpacerTrainResultHandler,
    SpacerClassifyResultHandler,
]


def handle_spacer_results(job_results: list[JobReturnMsg]):
    task_names_to_handler_classes = dict(
        (handler_class.job_name, handler_class)
        for handler_class in handler_classes
    )

    job_results_by_task_name = defaultdict(list)
    for job_res in job_results:
        job_results_by_task_name[
            job_res.original_job.task_name].append(job_res)

    for task_name, task_name_job_results in job_results_by_task_name.items():
        if task_name in task_names_to_handler_classes:
            handler_class = task_names_to_handler_classes[task_name]
            handler_class().handle_job_results(task_name_job_results)
        else:
            logger.error(f"Spacer task name [{task_name}] not recognized")
