$(function() {
    $('#submit').click(function() {
        event.preventDefault();
        var form_data = new FormData($('#uploadform')[0]);
        $.ajax({
            xhr: function(){
                 var xhr = new window.XMLHttpRequest();
                   // Handle progress
                   //Upload progress
                 xhr.upload.addEventListener("progress", function(evt){
                     if (evt.lengthComputable) {
                        var percentComplete = evt.loaded / evt.total;
                        //Do something with upload progress
                        console.log("percentComplete", percentComplete);
                        $("#loading").html('<"img" src="/static/img/loading.gif">').end();
                     }
                 }, false);
                 //Download progress
                 xhr.addEventListener("progress", function(evt){
                      if (evt.lengthComputable) {
                        var percentComplete = evt.loaded / evt.total;
                        //Do something with download progress
                        console.log("percentComplete", percentComplete);
                      }
                 }, false);

                 return xhr;
              },
            type: 'POST',
            url: '/uploadajax',
            data: form_data,
            contentType: false,
            processData: false,
            dataType: 'json'
        }).done(function(data, textStatus, jqXHR){
            console.log(data);
            console.log(textStatus);
            console.log(jqXHR);
            console.log('Success!');
            $("#resultFilename").text(data['name']);
            $("#resultFilesize").text(data['size']);
            $("#convert").attr('name',data['name'])
        }).fail(function(data){
            alert('error!');
        });
    });

    $('#convert').click(function() {
        event.preventDefault();
        var form_data = {'name': $("#convert").attr('name') }
        console.log(form_data)
        $.ajax({
            type: 'POST',
            url: '/convert',
            data: JSON.stringify(form_data),
            contentType: false,
            processData: false,
            dataType: 'json'
        }).done(function(data, textStatus, jqXHR){
            console.log(data);
            console.log(textStatus);
            console.log(jqXHR);
            console.log('Success!');
            $("#resultConvertion").text(data['name']);
            var download_link =  "/download/"+ data['name']
            $("#resultConvertion").attr("href", download_link);
        }).fail(function(data){
            alert('error!');
        });
    });
}); 