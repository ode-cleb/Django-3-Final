$(function () {
  function getCookie(name) {
    let value = null;
    document.cookie.split(';').forEach(function (cookie) {
      const c = cookie.trim();
      if (c.startsWith(name + '=')) {
        value = decodeURIComponent(c.slice(name.length + 1));
      }
    });
    return value;
  }

  const csrftoken = getCookie('csrftoken');

  $.ajaxSetup({
    beforeSend: function (xhr, settings) {
      if (!/^(GET|HEAD|OPTIONS|TRACE)$/.test(settings.type)) {
        xhr.setRequestHeader('X-CSRFToken', csrftoken);
      }
    }
  });

  const $container = $('#account-container');

  $container.on('submit', '#login-form', function (e) {
    e.preventDefault();
    const $form = $(this);
    $.ajax({
      url: $form.attr('action'),
      type: 'POST',
      data: $form.serialize(),
      success: function (resp) {
        $container.html(resp.html);
      },
      error: function (xhr) {
        const errors = xhr.responseJSON && xhr.responseJSON.errors;
        renderErrors(errors);
      }
    });
  });

  $container.on('click', '#logout-btn', function (e) {
    e.preventDefault();
    $.ajax({
      url: $(this).data('url'),
      type: 'POST',
      success: function (resp) {
        $container.html(resp.html);
      }
    });
  });

  function renderErrors(errors) {
    const $box = $('#form-errors').empty();
    if (!errors) { $box.text('An error occurred.'); return; }
    Object.keys(errors).forEach(function (field) {
      errors[field].forEach(function (msg) {
        $box.append($('<div>').text(msg));
      });
    });
  }
});