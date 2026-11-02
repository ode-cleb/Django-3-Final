// Côté navigateur du chat (ex01 à ex04).
// Uniquement jQuery + WebSocket natif : aucune requête AJAX.
//
// Rafraîchissement de la page (F5) : le navigateur efface tout, donc on garde dans
// sessionStorage (propre à l'onglet) ce qui est affiché ainsi que l'id du dernier
// message vu. À la reconnexion on le signale au serveur (?last=N) ; s'il confirme
// qu'il s'agit d'une reprise ("resumed"), on réaffiche tout ce qui était à l'écran
// puis les messages manqués. Un nouvel arrivant n'a rien en mémoire : il voit
// seulement les 3 derniers messages envoyés par le serveur (ex02).
$(function () {
  const MAX_ENTRIES = 500;                       // limite de ce qu'on garde en mémoire
  const storageKey = 'chat:' + window.CHAT_ROOM_ID;

  // État sauvegardé : {last: id du dernier message vu, entries: [{kind, user, text}]}
  function loadState() {
    try {
      const state = JSON.parse(sessionStorage.getItem(storageKey));
      if (state && Array.isArray(state.entries) && Number.isInteger(state.last)) {
        return state;
      }
    } catch (err) { /* sessionStorage indisponible ou contenu invalide */ }
    return null;
  }
  function saveState() {
    try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (err) {}
  }

  let state = loadState();  // null si c'est une vraie première arrivée dans la room

  // ws:// en HTTP, wss:// en HTTPS. L'id de la room est injecté par room.html.
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(
    scheme + '://' + location.host + '/ws/chat/' + window.CHAT_ROOM_ID + '/' +
    (state ? '?last=' + state.last : '')
  );

  const $messages = $('#messages');   // liste des messages (ex04 : taille fixe + scroll)
  const $userList = $('#user-list');  // liste des connectés (ex03), conteneur séparé

  // Ex04 : place la barre de scroll tout en bas pour voir les derniers messages.
  function scrollToBottom() {
    $messages.scrollTop($messages[0].scrollHeight);
  }

  // Affiche une entrée À LA SUITE des autres (jamais de remplacement), donc l'ordre
  // ancien -> récent est respecté. .text() évite l'injection de HTML.
  //  - kind 'message' : "user: texte"
  //  - kind 'system'  : "X has joined/left the chat"
  function render(entry) {
    if (entry.kind === 'system') {
      $messages.append($('<div class="system">').text(entry.text));
    } else {
      $messages.append(
        $('<div>').append($('<strong>').text(entry.user + ': '),
                          document.createTextNode(entry.text))
      );
    }
  }

  // Affiche une entrée ET la mémorise pour pouvoir la réafficher après un F5.
  function push(entry, id) {
    state.entries.push(entry);
    if (state.entries.length > MAX_ENTRIES) { state.entries.shift(); }
    if (id > state.last) { state.last = id; }
    saveState();
    render(entry);
  }

  // Réception d'un message du serveur : le champ "type" indique quoi en faire
  // (voir consumers.py pour la liste des types).
  socket.onmessage = function (e) {
    const data = JSON.parse(e.data);
    if (data.type === 'history') {
      // Rien n'est affiché avant ce premier message : c'est lui qui dit s'il s'agit
      // d'une reprise (on réaffiche l'écran d'avant) ou d'une vraie arrivée.
      if (data.resumed && state) {
        state.entries.forEach(render);
      } else {
        state = {last: 0, entries: []};
      }
      // Ex02 (nouvel arrivant : 3 derniers messages) ou messages manqués (reprise),
      // déjà triés du plus ancien au plus récent.
      data.messages.forEach(function (m) {
        push({kind: 'message', user: m.user, text: m.message}, m.id);
      });
      saveState();
    } else if (data.type === 'message') {
      push({kind: 'message', user: data.user, text: data.message}, data.id);
    } else if (data.type === 'system') {
      push({kind: 'system', text: data.message}, 0);
    } else if (data.type === 'users') {
      // Ex03 : on reconstruit toute la liste des connectés.
      $userList.empty();
      data.users.forEach(function (name) {
        $userList.append($('<li>').text(name));
      });
    }
    scrollToBottom();
  };

  // Le serveur a fermé la connexion (ou le réseau a coupé). Message affiché mais
  // non mémorisé : il ne doit pas réapparaître après un rafraîchissement.
  socket.onclose = function () {
    render({kind: 'system', text: 'Connection closed.'});
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
