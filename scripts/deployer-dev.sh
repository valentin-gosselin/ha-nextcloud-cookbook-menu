#!/usr/bin/env bash
# Déploie le composant dans le Home Assistant de dev (Dev, .20) puis redémarre le conteneur.
# Usage : scripts/deployer-dev.sh   (depuis le Dev, à la racine du dépôt)
set -euo pipefail

racine="$(cd "$(dirname "$0")/.." && pwd)"
source_composant="$racine/custom_components/nextcloud_cookbook_menu/"
cible="${HA_DEV_CONFIG:-/docker/homeassistant/config}/custom_components/nextcloud_cookbook_menu/"
conteneur="${HA_DEV_CONTENEUR:-homeassistant}"
delai="${HA_DEV_DELAI:-180}"

mkdir -p "$cible"
rsync -a --delete --exclude '__pycache__' "$source_composant" "$cible"
echo "Composant copié vers $cible"

debut=$(date +%s)
docker restart "$conteneur" >/dev/null
echo "Redémarrage de $conteneur..."

# HA est prêt quand l'API répond (401 sans jeton = serveur HTTP démarré).
until docker exec "$conteneur" python3 -c "import urllib.request,urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:8123/api/', timeout=3)
except urllib.error.HTTPError:
    pass" 2>/dev/null; do
  if (( $(date +%s) - debut > delai )); then
    echo "ERREUR : Home Assistant n'a pas répondu en ${delai} s" >&2
    docker logs --tail 50 "$conteneur" >&2
    exit 1
  fi
  sleep 3
done
echo "Home Assistant répond après $(( $(date +%s) - debut )) s"

if docker logs --since "${delai}s" "$conteneur" 2>&1 | grep -i "nextcloud_cookbook_menu" | grep -iE "error|exception"; then
  echo "ATTENTION : erreurs liées à nextcloud_cookbook_menu dans les journaux (voir ci-dessus)" >&2
  exit 2
fi
echo "Aucune erreur liée à nextcloud_cookbook_menu dans les journaux"
