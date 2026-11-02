// jQuery + native WebSocket only (no AJAX).
$(function () {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(
    scheme + '://' + location.host + '/ws/chat/' + window.CHAT_ROOM_ID + '/'
  );

  const $messages = $('#messages');
  const $userList = $('#user-list');

  // Ex04: keep the latest messages in view.
  function scrollToBottom() {
    $messages.scrollTop($messages[0].scrollHeight);
  }

  function addMessage(user, text) {
    $messages.append(
      $('<div>').append($('<strong>').text(user + ': '), document.createTextNode(text))
    );
  }

  function addSystem(text) {
    $messages.append($('<div class="system">').text(text));
  }

  socket.onmessage = function (e) {
    const data = JSON.parse(e.data);
    if (data.type === 'history') {
      data.messages.forEach(function (m) { addMessage(m.user, m.message); });
    } else if (data.type === 'message') {
      addMessage(data.user, data.message);
    } else if (data.type === 'system') {
      addSystem(data.message);
    } else if (data.type === 'users') {
      $userList.empty();
      data.users.forEach(function (name) {
        $userList.append($('<li>').text(name));
      });
    }
    scrollToBottom();
  };

  socket.onclose = function () {
    addSystem('Connection closed.');
    scrollToBottom();
  };

  $('#chat-form').on('submit', function (e) {
    e.preventDefault();
    const $input = $('#chat-input');
    const text = $.trim($input.val());
    if (text && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ message: text }));
      $input.val('');
    }
  });
});
