# Test multi-drones

Le script `test-multi-drones.js` verifie le routage de l'API avec **deux couples relais-drone** : le relais A est lie au drone A, et le relais B au drone B.

## Avant de lancer le test

- Demarrer PostgreSQL et l'API.
- Installer les dependances avec `npm install`.

Le script cree lui-meme deux drones, deux relais, un dashboard et les deux liens. Il supprime ces appareils a la fin, meme si une verification echoue.

Dans le terminal PowerShell :

```powershell
# Facultatif si l'API n'ecoute pas sur localhost:7281 :
$env:API_URL = "http://localhost:7281"

npm run test:multi-drones
```

## Ce que le script verifie

1. Le script cree deux couples relais-drone, puis les deux relais se connectent et annoncent chacun le bon drone autorise.
2. Deux connexions dashboard s'abonnent, une au drone A et l'autre au drone B.
3. Chaque relais envoie une telemetrie fictive. Seul le dashboard abonne au drone concerne doit la recevoir.
4. Le relais A tente d'envoyer une telemetrie pour le drone B : l'API doit la refuser.
5. Le dashboard envoie une commande `Stop` a chaque drone. Elle doit arriver uniquement au relais associe.

Le script affiche `OK` si toutes les verifications passent, ou `ECHEC` avec la raison sinon. Il teste le routage dans l'API : il ne commande pas un vol et ne verifie pas la livraison MAVLink au drone.
