/**
 * Avicenne Pay - Scripts globaux
 */

// 1. Gestion de la visibilité des mots de passe
// Utilisé dans profile.html, login.html et admin/user_form.html
function toggleVisibility(fieldId, btn) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    
    if (field.type === 'password') {
        field.type = 'text';
        btn.innerHTML = '<i class="bi bi-eye-slash"></i>';
    } else {
        field.type = 'password';
        btn.innerHTML = '<i class="bi bi-eye"></i>';
    }
}

// 2. Initialisations au chargement du DOM
document.addEventListener('DOMContentLoaded', function() {
    
    // Auto-fermeture des alertes (ex: message "profil incomplet") après 8 secondes
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 8000);
    });

    // Activation des tooltips Bootstrap (si tu en utilises)
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    console.log("Avicenne Pay JS : Initialisé avec succès");
});

// 3. Utilitaires pour l'administration
function confirmAction(message) {
    return confirm(message || "Êtes-vous sûr de vouloir effectuer cette action ?");
}

// 4. Formatage des nombres pour l'affichage (ex: 1250.5 -> 1 250,50 €)
function formatMoney(amount) {
    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency: 'EUR',
    }).format(amount);
}

// 5. Confirmations d'actions administratives
function confirmDelete(button) {
    Swal.fire({
        title: "Supprimer ?",
        text: "Attention, cette suppression est définitive",
        icon: "warning",
        width: '300px',
        showCancelButton: true,
        confirmButtonColor: "#ffca2c", // Le jaune d'Avicenne Pay
        cancelButtonColor: "#6c757d",
        confirmButtonText: "Oui, supprimer",
        cancelButtonText: "Annuler",
        customClass: {
            confirmButton: 'text-dark fw-bold' // Pour que le texte noir ressorte sur le jaune
        }
    }).then((result) => {
        // .isConfirmed est vrai si l'utilisateur a cliqué sur le bouton jaune
        if (result.isConfirmed) {
            button.closest('form').submit();
        }
    });
}

// Fonction pour le Renvoi (Soumise -> Brouillon)
function confirmReopen(button) {
    const form = button.closest('form');
    const textarea = form.querySelector('textarea[name="commentaire_admin"]');
    const motif = textarea.value.trim();

    textarea.classList.remove('is-invalid', 'border-danger');

    if (motif.length < 5) {
        textarea.classList.add('is-invalid', 'border-danger');
        textarea.focus();

        Swal.fire({
            icon: 'warning',
            title: 'Commentaire obligatoire',
            text: 'Veuillez préciser la raison (min. 5 caractères).',
            confirmButtonColor: '#ffca2c', // Jaune Avicenne
            customClass: { confirmButton: 'text-dark fw-bold' }
        });
        return;
    }

    Swal.fire({
        title: "Confirmer la réouverture ?",
        text: "La déclaration redeviendra un brouillon modifiable.",
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#ffca2c", // Jaune Avicenne
        cancelButtonColor: "#6c757d",
        confirmButtonText: "Oui, réouvrir",
        cancelButtonText: "Annuler",
        customClass: { confirmButton: 'text-dark fw-bold' }
    }).then((result) => {
        if (result.isConfirmed) {
            form.submit();
        }
    });
}

function confirmDesactivation(userId, userEmail) {
    Swal.fire({
        title: 'Désactivation du compte',
        html: `Voulez-vous <strong>désactiver</strong> cet utilisateur ?<br><small class="text-muted">${userEmail}</small>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#dc3545', // Rouge Bootstrap
        cancelButtonColor: '#6c757d', // Gris Bootstrap
        confirmButtonText: 'Oui, désactiver',
        cancelButtonText: 'Annuler',
        reverseButtons: true,
        focusCancel: true 
    }).then((result) => {
        if (result.isConfirmed) {
            // On soumet le formulaire de désactivation
            document.getElementById(`desac-form-${userId}`).submit();
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    // 1. On récupère les paramètres de l'URL
    const urlParams = new URLSearchParams(window.location.search);
    const msgKey = urlParams.get('msg');

    // 2. Dictionnaire de messages
   const toastMessages = {
    'rejetee': {
        title: 'Déclaration rejetée !',
        text: 'Le motif a bien été enregistré.',
        icon: 'warning'
    },
    'updated': {
        title: 'Mise à jour réussie',
        text: 'Les modifications ont été sauvegardées.',
        icon: 'success'
    },
    'deleted': {
        title: 'Supprimé !',
        text: 'L\'élément a bien été retiré du référentiel.',
        icon: 'success'
    }
};

    // 3. Le sélecteur automatique
    if (msgKey && toastMessages[msgKey]) {
        const config = toastMessages[msgKey];
        
        Swal.fire({
            width: '350px', // ✅ Ta largeur personnalisée
            confirmButtonColor: '#3085d6',
            ...config
        });
    }
    // ✨ Le nettoyage de l'URL
    const newUrl = window.location.pathname; // On ne garde que le chemin (ex: /declarations)
    window.history.replaceState({}, document.title, newUrl);
});

function exporterCSV() {
    // 1. Récupération des valeurs des sélecteurs (vérifie bien les IDs !)
    const annee = document.getElementById('filterAnnee')?.value || '';
    const mois = document.getElementById('filterMois')?.value || '';
    const site = document.getElementById('filterSite')?.value || '';

    // 2. Construction de l'URL avec les paramètres
    const params = new URLSearchParams();
    if (annee) params.append('annee', annee);
    if (mois) params.append('mois', mois);
    if (site) params.append('site', site);

    // 3. Déclenchement du téléchargement
    const url = `/admin/export/csv?${params.toString()}`;
    window.location.href = url;
}