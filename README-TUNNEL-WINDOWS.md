# 🌉 Configuration du tunnel AO-ID depuis Windows

Ce document explique comment accéder à l'application AO-ID depuis votre poste Windows via un tunnel SSH.

## 📋 Prérequis

- **OpenSSH** installé sur Windows (PowerShell 7+ ou Windows 10+ avec OpenSSH)
- **Accès SSH** à djinn-bot (`numa@djinn-bot` ou selon votre config)
- **Connexion réseau** vers djinn-bot (VPN ONE ID si nécessaire)

## 🚀 Lancement du tunnel

### Étape 1 : Téléchargez le script PowerShell

Le script `tunnel-ao-id.ps1` est disponible à :
- **Linux (djinn-bot)** : `/home/numa/projets/appel-offre/tunnel-ao-id.ps1`
- **Windows** : Copiez-le dans `C:\Users\n.doublet.ONE-ID\Downloads\`

### Étape 2 : Lancez le tunnel

Ouvrez **PowerShell** et exécutez :

```powershell
PowerShell -ExecutionPolicy Bypass -File "C:\Users\n.doublet.ONE-ID\Downloads\tunnel-ao-id.ps1"
```

Vous devriez voir :
```
2026-10-07 09:30:00 === Tunnel AO-ID démarré ===
2026-10-07 09:30:00 Ports redirigés: 8080 (AO-ID), 8081 (draw.io)
2026-10-07 09:30:00 Tentative de connexion #1...
```

### Étape 3 : Accédez à l'application

Une fois le tunnel établi, ouvrez votre navigateur :

- **AO-ID** : http://localhost:8080
- **Draw.io** : http://localhost:8081

## 📊 Logs et diagnostic

Les logs sont stockés dans : `C:\Users\n.doublet.ONE-ID\Downloads\tunnel-ao-id.log`

Vérifiez-les pour diagnostiquer les problèmes de connexion.

## 🔧 Configuration

Le script se configure automatiquement, mais vous pouvez modifier :
- `numa@djinn-bot` si votre login SSH est différent
- Les ports `8080` / `8081` si nécessaire

## ❌ Résolution de problèmes

| Problème | Cause | Solution |
|----------|------|----------|
| "Permission denied (publickey)" | Clés SSH non configurées | Assurez-vous que SSH keys sont générées et copiées sur djinn-bot |
| "Connection timed out" | djinn-bot injoignable | Vérifiez la connexion VPN ONE ID |
| "Port already in use" | Tunnel ou application déjà active | Fermez le tunnel précédent ou changez le port dans le script |

## 📝 Notes

- Le script se relance automatiquement si la connexion tombe
- Gardez la fenêtre PowerShell ouverte tant que vous avez besoin du tunnel
- Ctrl+C pour arrêter le tunnel

---

**Géré en autonomie par Hermes** — dernière mise à jour : 2026-10-07
