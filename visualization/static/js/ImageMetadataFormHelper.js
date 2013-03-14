// Selects all of the checkboxes given the value of the check all box.
function selectall() {
    var id = "#id_selectAll";
    if ($(id).attr('checked'))
        setCheckedRows(true);
    else
        setCheckedRows(false);
}

// Given the row/column, this will return the value at that cell in the table.
function getValueFromCell(row, column)
{
    return $('#metadataFormTable')[0].rows[row+1].cells[column+1].childNodes[0].value;
}

// Given the row/column, this sets the value in that cell to what value is.
function setValueFromCell(row, column, value)
{
    $('#metadataFormTable')[0].rows[row+1].cells[column+1].childNodes[0].value = value;
}

// This returns an bool array that represents what checkboxes are checked.
function checkedRows() {
    var rows = $("#metadataFormTable tr").length;
    var checkedRows = new Array();
    for (var i = 0; i < rows; i++)
    {
        var id = "#id_form-" + i + "-selected";
        if ($(id).attr('checked') != null)
            checkedRows[i] = true;
        else
            checkedRows[i] = false;
    }
    return checkedRows;
}

// Takes a boolean value that sets all of the checkboxes to that value.
function setCheckedRows(checked) {
    var rows = $("#metadataFormTable tr").length;
    for (var i = 0; i < rows; i++)
    {
        var id = "#id_form-" + i + "-selected";
        $(id).attr("checked", checked);
    }
}

// This will handle updating all checked rows in the form. This is called whenever a user
// types in one of the text fields.
function justTyped(row, column) {
    var checked = checkedRows();
    if (checked[row] == false) return;
    var input = getValueFromCell(row, column);
    for (var i = 0; i < checked.length; i++)
    {
        if(checked[i] == true) setValueFromCell(i, column, input);
    }
}

// This initializes the form with the correct bindings.
function setUpBindings() {
    var images = $("#metadataFormTable tr").length;
    var fields = $("#metadataFormTable tr")[0].cells.length;
    var id;
    for (var i = 1; i < images; i++)
    {
        for (var j = 2; j < fields; j++)
        {
            id = '#' + $('#metadataFormTable')[0].rows[i].cells[j].childNodes[0].getAttribute('id');
            if (j == 3)
            {
                $(id).datepicker({ dateFormat: 'yy-mm-dd' });
                setRowColumnBindingsChange(id);
            }
            else setRowColumnBindingsKeyUp(id);
        }
    }
    id = "#id_selectAll";
    $(id).bind("change", function() {
        selectall()
    });
/*  For later use (ajax)
    id = "#id_view";
    $(id).bind("change", function() {
        ajax(ajax_url);
    });*/
}

// Given the id, this will set a key down key binding that calls justTyped with the
// given row and column of the table form.
function setRowColumnBindingsKeyUp(id) {
    $(id).bind("keyup", function() {
        var row_index = $(this).parent().parent().index('tr');
        var col_index = $(this).parent().index('tr:eq('+row_index+') td');
        justTyped(row_index-1, col_index-1);
    });
}

function setRowColumnBindingsChange(id) {
    $(id).bind("change", function() {
        var row_index = $(this).parent().parent().index('tr');
        var col_index = $(this).parent().index('tr:eq('+row_index+') td');
        justTyped(row_index-1, col_index-1);
    });
}

/* For later use (ajax)
function ajax(url) {

    var checked = $("#id_view").attr('checked');
    $.ajax({
        type: "POST",
        url:url,
        data: {
            'checked': checked
        },
        success: function(data){
            $("#result").val(data.result);
        },
        error: function(request){
            console.log(request.responseText);
        }
    });
}
*/