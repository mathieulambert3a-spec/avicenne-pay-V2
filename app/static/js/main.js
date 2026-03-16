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
    // Si c'est un bouton dans un formulaire, on récupère le formulaire
    const form = button.closest('form');
    
    Swal.fire({
        title: "Supprimer ?",
        text: "Attention, cette suppression est définitive",
        icon: "warning", // 'warning' au lieu de 'danger'
        width: '300px',
        showCancelButton: true,
        confirmButtonColor: "#ffca2c",
        cancelButtonColor: "#6c757d",
        confirmButtonText: "Oui, supprimer",
        cancelButtonText: "Annuler",
        customClass: {
            confirmButton: 'text-dark fw-bold'
        }
    }).then((result) => {
        if (result.isConfirmed && form) {
            form.submit(); // On ne soumet que si l'utilisateur valide
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
        confirmButtonColor: '#dc3545', 
        confirmButtonText: 'Oui, désactiver',
        cancelButtonText: 'Annuler',
        customClass: {
            confirmButton: 'fw-bold'
        }
    }).then((result) => {
        if (result.isConfirmed) {
            document.getElementById(`desac-form-${userId}`).submit();
        }
    });
}

// Fonction pour la Validation finale (Soumise -> Validée)
function confirmValidate(button) {
    const form = button.closest('form');
    
    Swal.fire({
        title: "Valider la déclaration ?",
        text: "Cette action confirmera les montants pour la mise en paie.",
        icon: "question",
        showCancelButton: true,
        confirmButtonColor: "#198754", // Vert succès
        cancelButtonColor: "#6c757d",
        confirmButtonText: "Oui, valider",
        cancelButtonText: "Annuler",
        customClass: {
            confirmButton: 'fw-bold'
        }
    }).then((result) => {
        if (result.isConfirmed && form) {
            form.submit();
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const msgKey = urlParams.get('msg');

    const toastMessages = {
        'created': {
        title: 'Utilisateur créé !',
        text: 'Le compte a été enregistré et un mail d\'activation a été envoyé.',
        icon: 'success',
        confirmButtonColor: '#198754'
        },
        'declaration_created': { // TA NOUVELLE CLÉ ICI
        title: 'Déclaration enregistrée !',
        text: 'Votre brouillon a été créé avec succès.',
        icon: 'success',
        confirmButtonColor: '#198754'
        }, 
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
        'submitted': {
            title: 'Déclaration transmise !',
            text: 'Votre déclaration a bien été envoyée pour validation.',
            icon: 'success'
        },
        'deleted': {
            title: 'Supprimé !',
            text: "L'élément a bien été retiré du référentiel.",
            icon: 'success'
        },
        'validee': {
            title: 'Déclaration validée !',
            text: 'Elle est désormais verrouillée pour la paie.',
            icon: 'success',
            confirmButtonColor: '#198754'
        },
        'saved_as_draft_early': {
            title: 'Soumission impossible',
            text: "La soumission n'est possible qu'à partir du 1er du mois concerné. Vos modifications ont été sauvegardées en BROUILLON.",
            icon: 'info',
            confirmButtonColor: '#ffca2c'
        }
    };

    if (msgKey && toastMessages[msgKey]) {
        const config = toastMessages[msgKey];
        
        Swal.fire({
            width: '350px',
            confirmButtonColor: '#3085d6', // Bleu par défaut, écrasé par config si besoin
            ...config,
            customClass: { confirmButton: 'fw-bold' }
        }).then(() => {
            // ✨ LE NETTOYAGE SE FAIT ICI, APRÈS LE CLIC SUR OK
            const newUrl = window.location.pathname;
            window.history.replaceState({}, document.title, newUrl);
        });
    }
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
// Gestion de l'édition des missions parents
document.addEventListener('DOMContentLoaded', function() {
    const btnEditParents = document.querySelectorAll('.btn-edit-parent');
    btnEditParents.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation(); 

            const mid = this.dataset.parentId;
            const mname = this.dataset.parentName;
            const mresp = this.dataset.isResp === 'true';

            const modalEl = document.getElementById('modalEditMission');
            const form = document.getElementById('formEditMission');

            if (modalEl && form) {
                // 1. On ajoute l'attribut pour le CSS
                modalEl.setAttribute('data-mode', 'edit');
                
                // 2. On remplit le formulaire
                form.action = `/admin/referentiel/missions/${mid}/edit`;
                document.getElementById('editParentNameInput').value = mname;
                document.getElementById('editFlexSwitchResp').checked = mresp;

                // 3. On affiche la modale
                const modal = new bootstrap.Modal(modalEl);
                modal.show();
            }
        });
    });

    // Nettoyage automatique quand on ferme la modale pour que le mode "Ajout" reste normal
    const modalEdit = document.getElementById('modalEditMission');
    if (modalEdit) {
        modalEdit.addEventListener('hidden.bs.modal', function () {
            modalEdit.removeAttribute('data-mode');
        });
    }
});
/**
 * Déclenche la génération des factures avec un retour visuel (SweetAlert2)
*/
function lancerGenerationFactures() {
    const form = document.getElementById('formFacturation');
    if (!form) return;

    const dateDebut = form.querySelector('[name="date_debut"]').value;
    const dateFin = form.querySelector('[name="date_fin"]').value;

    if (!dateDebut || !dateFin) {
        Swal.fire({
            icon: 'warning',
            title: 'Champs incomplets',
            text: 'Veuillez sélectionner les dates.',
            confirmButtonColor: '#ffca2c'
        });
        return;
    }

    // 1. Affichage du loader
    Swal.fire({
        title: 'Génération en cours...',
        text: 'Veuillez patienter, nous préparons votre archive ZIP.',
        icon: 'info',
        allowOutsideClick: false,
        showConfirmButton: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    // 2. Soumission réelle du formulaire
    form.submit();

    // 3. Fermeture automatique du loader
    // On attend 5 secondes (temps moyen pour que le serveur commence à répondre)
    // puis on ferme l'alerte. Le téléchargement continuera en arrière-plan.
    setTimeout(() => {
        Swal.close();
        
        // Fermer la modal Bootstrap si elle est ouverte
        const modalEl = document.getElementById('modalFactures');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }
    }, 5000); 
}

function lancerRelances() {
    Swal.fire({
        title: 'Relance des retardataires',
        text: "Envoyer un email de rappel à tous ceux qui n'ont pas encore déclaré ce mois-ci ?",
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#0d6efd',
        cancelButtonColor: '#6c757d',
        confirmButtonText: '<i class="bi bi-send"></i> Oui, envoyer',
        cancelButtonText: 'Annuler',
        reverseButtons: true
    }).then((result) => {
        if (result.isConfirmed) {
            Swal.fire({
                title: 'Envoi en cours',
                html: 'Veuillez patienter...',
                allowOutsideClick: false,
                didOpen: () => { Swal.showLoading() }
            });

            // On utilise l'URL correcte de ton backend FastAPI
            fetch('/admin/relance-retardataires', { method: 'POST' })
            .then(async response => {
                const data = await response.json();
                if (response.ok) {
                    // On affiche le nombre de personnes relancées si le back le renvoie
                    Swal.fire('Succès !', data.message || `${data.count} emails envoyés.`, 'success');
                } else {
                    Swal.fire('Erreur', data.detail || 'Une erreur est survenue', 'error');
                }
            })
            .catch(error => {
                Swal.fire('Erreur technique', 'Le serveur ne répond pas.', 'error');
            });
        }
    })
}