# Optimisation du prompt LLM pour l'étape Focus administratif

## Analyse du prompt actuel

Le prompt actuel dans `app/recap_admin.py` est très complet mais ne permet pas d'afficher les éléments souhaités. 

## Modifications proposées

1. **Backend** : Ajouter le retour du prompt et de la réponse brute dans les réponses API
2. **Frontend** : Afficher le prompt et la réponse IA à côté du bouton "Générer"
3. **Interface** : Créer une section dédiée à l'affichage de ces éléments

## Implémentation

### 1. Modification du backend (app/main.py)

Ajouter les champs `prompt` et `raw` dans les réponses de `/api/recap-admin` :

```python
# Dans la fonction recap_admin(), avant le return :
return {**res, "raw": "..." if res["ok"] else (raw or "")[:4000], "prompt": admin_mod.RECAP_ADMIN_PROMPT}
```

### 2. Modification de l'interface HTML (app/web/index.html)

Ajouter une section pour afficher les éléments :
```html
<!-- Section d'affichage du prompt et réponse IA -->
<div id="adminPromptSection" style="display:none; margin-top:15px; padding:12px; background:#f8f9fa; border-radius:8px; border-left:4px solid #1e7e34;">
  <h3 style="margin:0 0 8px 0; font-size:14px; color:#1e7e34;">Prompt IA</h3>
  <div id="adminPromptDisplay" style="font-family:monospace; font-size:12px; background:#fff; padding:8px; border-radius:4px; white-space:pre-wrap; max-height:200px; overflow:auto;"></div>
  <h3 style="margin:12px 0 8px 0; font-size:14px; color:#1e7e34;">Réponse IA</h3>
  <div id="adminResponseDisplay" style="font-family:monospace; font-size:12px; background:#fff; padding:8px; border-radius:4px; white-space:pre-wrap; max-height:200px; overflow:auto;"></div>
</div>
```

### 3. Ajout de la logique JavaScript

Dans le fichier index.html, ajouter après la fonction `genAdmin()` :
```javascript
function showAdminPromptResponse(prompt, response) {
  const section = $('adminPromptSection');
  if (!section) return;
  
  const promptDisplay = $('adminPromptDisplay');
  const responseDisplay = $('adminResponseDisplay');
  
  if (promptDisplay) promptDisplay.textContent = prompt.substring(0, 2000);
  if (responseDisplay) responseDisplay.textContent = response.substring(0, 2000);
  
  section.style.display = 'block';
}

// Dans genAdmin(), après l'appel à l'API, ajouter :
if (d.prompt) showAdminPromptResponse(d.prompt, d.raw || '');
```

## Résultat attendu

Lorsque l'utilisateur clique sur "Générer le focus administratif (IA)", les éléments suivants seront affichés :
1. Le prompt système complet utilisé par l'IA
2. La réponse brute de l'IA (si elle est exploitable)
3. Un message d'erreur clair si la réponse n'est pas exploitable