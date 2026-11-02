// Côté navigateur du chat (ex01 à ex04).
// Uniquement jQuery + WebSocket natif : aucune requête AJAX.
$(function () {
  // ws:// en HTTP, wss:// en HTTPS. L'id de la room est injecté par room.html.
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(
    scheme + '://' + location.host + '/ws/chat/' + window.CHAT_ROOM_ID + '/'
  );

  const $messages = $('#messages');   // liste des messages (ex04 : taille fixe + scroll)
  const $userList = $('#user-list');  // liste des connectés (ex03), conteneur séparé

  // Ex04 : place la barre de scroll tout en bas pour voir les derniers messages.
  function scrollToBottom() {
    $messages.scrollTop($messages[0].scrollHeight);
  }

  // Ajoute "user: texte" À LA SUITE des autres (jamais de remplacement), donc
  // l'ordre ancien -> récent est respecté. .text() évite l'injection de HTML.
  function addMessage(user, text) {
    $messages.append(
      $('<div>').append($('<strong>').text(user + ': '), document.createTextNode(text))
    );
  }

  // Message système ("X has joined the chat" / "X has left the chat").
  function addSystem(text) {
    $messages.append($('<div class="system">').text(text));
  }

  // Réception d'un message du serveur : le champ "type" indique quoi en faire
  // (voir consumers.py pour la liste des types).
  socket.onmessage = function (e) {
    const data = JSON.parse(e.data);
    if (data.type === 'history') {
      // Ex02 : les derniers messages, déjà triés du plus ancien au plus récent.
      data.messages.forEach(function (m) { addMessage(m.user, m.message); });
    } else if (data.type === 'message') {
      addMessage(data.user, data.message);
    } else if (data.type === 'system') {
      addSystem(data.message);
    } else if (data.type === 'users') {
      // Ex03 : on reconstruit toute la liste des connectés.
      $userList.empty();
      data.users.forEach(function (name) {
        $userList.append($('<li>').text(name));
      });
    }
    scrollToBottom();
  };

  // Le serveur a fermé la connexion (ou le réseau a coupé).
  socket.onclose = function () {
    addSystem('Connection closed.');
    scrollToBottom();
  };

  // Envoi d'un message : on l'envoie au serveur, qui le renverra à tout le
  // monde (y compris nous) ; c'est à ce moment qu'il s'affiche.
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
