// Ex00 – connexion / déconnexion 100 % AJAX (jQuery), sans jamais recharger la page.
//
// Principe : le serveur renvoie du JSON {html: "..."} contenant le nouveau
// morceau de page (formulaire OU "Logged as ..."), et on le met dans
// #account-container. Au rechargement manuel (F5), c'est le template
// account.html qui choisit le bon morceau selon user.is_authenticated.
$(function () {
  // Lit un cookie par son nom (utilisé pour récupérer le jeton CSRF).
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

  // Django exige un jeton CSRF sur tous les POST. On l'ajoute en en-tête
  // X-CSRFToken à chaque requête non "sûre" (POST ici).
  // IMPORTANT (bug corrigé) : on relit le cookie à CHAQUE requête. Django
  // change le jeton lors d'un login() / logout() ; l'ancienne version le lisait
  // une seule fois au chargement, donc le logout suivant était refusé (403)
  // tant qu'on ne rafraîchissait pas la page.
  $.ajaxSetup({
    beforeSend: function (xhr, settings) {
      if (!/^(GET|HEAD|OPTIONS|TRACE)$/.test(settings.type)) {
        xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
      }
    }
  });

  const $container = $('#account-container');

  // Soumission du formulaire de login : on bloque l'envoi classique (qui
  // rechargerait la page) et on envoie les champs en POST via AJAX.
  // On utilise la délégation d'événement ($container.on(..., '#login-form'))
  // car le formulaire est remplacé dynamiquement après chaque login/logout.
  $container.on('submit', '#login-form', function (e) {
    e.preventDefault();
    const $form = $(this);
    $.ajax({
      url: $form.attr('action'),
      type: 'POST',
      data: $form.serialize(),
      success: function (resp) {
        // Login OK : le formulaire disparaît, "Logged as <user>" + Logout apparaissent.
        $container.html(resp.html);
      },
      error: function (xhr) {
        // Login refusé (HTTP 400) : on affiche les erreurs du formulaire.
        const errors = xhr.responseJSON && xhr.responseJSON.errors;
        renderErrors($('#form-errors'), errors);
      }
    });
  });

  // Bouton "Create user" / "Back" : on affiche l'un des deux blocs et on cache
  // l'autre avec l'attribut "hidden" (tout est déjà dans la page, pas de requête serveur).
  $container.on('click', '#show-register', function () {
    $('#login-box').prop('hidden', true);
    $('#register-box').prop('hidden', false);
  });
  $container.on('click', '#show-login', function () {
    $('#register-box').prop('hidden', true);
    $('#login-box').prop('hidden', false);
  });

  // Création d'utilisateur : POST AJAX. Succès -> l'utilisateur est créé et
  // connecté, on affiche "Logged as ..." ; erreur -> messages dans #register-errors.
  $container.on('submit', '#register-form', function (e) {
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
        renderErrors($('#register-errors'), xhr.responseJSON && xhr.responseJSON.errors);
      }
    });
  });

  // Clic sur Logout : POST AJAX, puis on remplace la phrase + le bouton par le
  // formulaire de login renvoyé par le serveur.
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

  // Affiche les erreurs ({champ: [messages]}) dans la zone $box donnée.
  // .text() (et non .html()) évite toute injection de HTML.
  function renderErrors($box, errors) {
    $box.empty();
    if (!errors) { $box.text('An error occurred.'); return; }
    Object.keys(errors).forEach(function (field) {
      errors[field].forEach(function (msg) {
        $box.append($('<div>').text(msg));
      });
    });
  }
});
