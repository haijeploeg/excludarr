$(document).ready(function(){
    $(document).on('click', '#run', function(){
        $('#run').prop('disabled', true);
        $.ajax({
            type: 'POST',
            url: url_name,
            data: {
                'csrfmiddlewaretoken': csrf_token
            },
            complete: function(){
              $('#run').prop('disabled', false);
            },
        });
    });
})