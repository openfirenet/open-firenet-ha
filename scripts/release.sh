#!/usr/bin/env bash
# ==============================================================================
# Open Firenet (Home Assistant integration) release script
#
# One command for a release, with guard rails:
# 1. Clean working tree, on main, in sync with origin
# 2. Unit tests, when the test environment is installed (CI runs them in any case)
# 3. Automatic SemVer (patch / minor / major) from the commits since the last tag
# 4. "version" of manifest.json set to the new version, and the "## Unreleased"
#    section of CHANGELOG.md renamed "## vX.Y.Z (date)"
# 5. Commit, annotated tag, push: the Release workflow then creates the GitHub
#    release as a draft, with the notes of that CHANGELOG section
#
# Usage: scripts/release.sh [auto|patch|minor|major|vX.Y.Z]
# ==============================================================================

set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}ℹ${NC} $*"; }
ok()    { echo -e "${GREEN}✔${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✖${NC} $*" >&2; }
fatal() { err "$*"; exit 1; }

MANIFEST="custom_components/open_firenet/manifest.json"
UNRELEASED="## Unreleased"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  fatal "Ce script doit être exécuté dans un dépôt Git."
fi
cd "$REPO_ROOT"

echo -e "\n${BOLD}${CYAN}=== Open Firenet (Home Assistant) Release Assistant ===${NC}\n"

# 1. Clean working tree
info "Vérification de l'état de l'arbre de travail Git..."
if [[ -n "$(git status --porcelain)" ]]; then
  fatal "L'arbre de travail n'est pas propre. Veuillez commiter ou remiser vos modifications avant de releaser."
fi
ok "Arbre de travail propre."

# 2. Branch
CURRENT_BRANCH="$(git branch --show-current)"
info "Branche actuelle : ${BOLD}${CURRENT_BRANCH}${NC}"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  warn "Vous n'êtes pas sur la branche 'main' (branche actuelle: $CURRENT_BRANCH)."
  read -rp "Voulez-vous vraiment créer une release depuis '$CURRENT_BRANCH' ? [o/N] " confirm_branch
  if [[ ! "$confirm_branch" =~ ^[oOyY]$ ]]; then
    fatal "Release annulée. Basculez sur 'main' avec : git checkout main"
  fi
fi

# 3. In sync with origin (tags included, so that the last version is the real one)
info "Vérification de la synchronisation avec origin..."
git fetch origin "$CURRENT_BRANCH" --tags --quiet
LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "origin/$CURRENT_BRANCH" 2>/dev/null || true)"
if [[ -n "$REMOTE_COMMIT" && "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]]; then
  BEHIND="$(git rev-list --count HEAD..origin/"$CURRENT_BRANCH")"
  if [[ "$BEHIND" -gt 0 ]]; then
    fatal "Votre branche locale a $BEHIND commit(s) de retard par rapport à origin. Faites un 'git pull' d'abord."
  fi
fi
ok "Synchronisation remote vérifiée."

# 4. Unit tests: they need Home Assistant's test environment (requirements_test.txt). Without it the release goes on,
#    as the Tests workflow runs them on every push.
if python3 -c "import pytest_homeassistant_custom_component" >/dev/null 2>&1; then
  info "Exécution de la suite de tests unitaires..."
  if python3 -m pytest -q >/dev/null 2>&1; then
    ok "Tous les tests unitaires sont passés avec succès."
  else
    python3 -m pytest -q || true
    fatal "Les tests unitaires ont échoué ! Release interrompue."
  fi
else
  warn "Environnement de test absent (pip install -r requirements_test.txt) : tests non lancés ici, la CI les exécute."
fi

# 5. Something to release: the CHANGELOG must have entries under "Unreleased"
[[ -f CHANGELOG.md ]] || fatal "CHANGELOG.md introuvable."
grep -q "^${UNRELEASED}\$" CHANGELOG.md || fatal "CHANGELOG.md n'a pas de section \"${UNRELEASED}\" : rien à publier."
NOTES="$(awk -v h="$UNRELEASED" '$0==h{f=1;next} /^## /{f=0} f' CHANGELOG.md | sed '/^[[:space:]]*$/d')"
if [[ -z "$NOTES" ]]; then
  fatal "La section \"${UNRELEASED}\" de CHANGELOG.md est vide : ajoutez-y les notes de version avant de releaser."
fi

# 6. Last tag and SemVer candidates
LATEST_TAG="$(git describe --tags --abbrev=0 2>/dev/null || true)"
if [[ -z "$LATEST_TAG" ]]; then
  warn "Aucun tag existant trouvé dans ce dépôt."
  LATEST_TAG="aucun"
  NEXT_PATCH="v0.0.1"; NEXT_MINOR="v0.1.0"; NEXT_MAJOR="v1.0.0"
else
  info "Dernier tag détecté : ${BOLD}${LATEST_TAG}${NC}"
  RAW_VER="${LATEST_TAG#v}"
  IFS='.' read -r MAJOR MINOR PATCH <<< "$RAW_VER"
  NEXT_PATCH="v${MAJOR}.${MINOR}.$((PATCH + 1))"
  NEXT_MINOR="v${MAJOR}.$((MINOR + 1)).0"
  NEXT_MAJOR="v$((MAJOR + 1)).0.0"
fi

# 7. Commits and notes since the last tag
echo ""
echo -e "${BOLD}Historique depuis ${LATEST_TAG} :${NC}"
COMMIT_LIST=""
if [[ "$LATEST_TAG" != "aucun" ]]; then
  COMMIT_LIST="$(git log --oneline "${LATEST_TAG}..HEAD" 2>/dev/null || true)"
  if [[ -n "$COMMIT_LIST" ]]; then echo "$COMMIT_LIST" | sed 's/^/  • /'; else echo "  (aucun nouveau commit)"; fi
  LOG_RANGE="${LATEST_TAG}..HEAD"
else
  git log -n 5 --oneline | sed 's/^/  • /'
  LOG_RANGE="HEAD"
fi
echo ""
echo -e "${BOLD}Notes de version (section \"${UNRELEASED}\") :${NC}"
echo "$NOTES" | sed 's/^/  /' | cut -c1-160
echo ""

# 8. Conventional Commits analysis (auto bump)
BREAKING_MATCHES="$(git log --format="%s%n%b" "$LOG_RANGE" 2>/dev/null | grep -E "^[a-zA-Z]+(\([^)]+\))?!:|^BREAKING[ -]CHANGE:" || true)"
FEAT_MATCHES="$(git log --format="%s" "$LOG_RANGE" 2>/dev/null | grep -E "^feat(\([^)]+\))?:|Merge pull request #[0-9]+ from [^/]+/feat/|Merge branch 'feat/" || true)"
if [[ -n "$BREAKING_MATCHES" ]]; then
  AUTO_DETECTED="major"; AUTO_REASON="présence de Breaking Change(s) (ex: type!: ou BREAKING CHANGE:)"
elif [[ -n "$FEAT_MATCHES" ]]; then
  AUTO_DETECTED="minor"; AUTO_REASON="présence de nouvelle(s) fonctionnalité(s) (commit(s) feat / branche feat)"
else
  AUTO_DETECTED="patch"; AUTO_REASON="correctifs ou maintenance (aucun commit feat ou breaking change)"
fi

# 9. Target: automatic by default, or forced by the argument
TARGET_TYPE="${1:-auto}"
case "$TARGET_TYPE" in
  auto)
    TARGET_TYPE="$AUTO_DETECTED"
    info "Incrément SemVer auto-détecté : ${BOLD}${CYAN}${TARGET_TYPE}${NC} (${AUTO_REASON})" ;;
  patch|minor|major)
    info "Incrément forcé par argument : ${BOLD}${TARGET_TYPE}${NC}" ;;
  v*.*.*|[0-9]*.*.*)
    info "Version explicite demandée : ${BOLD}${TARGET_TYPE}${NC}" ;;
  *)
    fatal "Type d'incrémentation inconnu : '$TARGET_TYPE'. Utilisation : $0 [auto|patch|minor|major|vX.Y.Z]" ;;
esac
case "$TARGET_TYPE" in
  patch) NEW_TAG="$NEXT_PATCH" ;;
  minor) NEW_TAG="$NEXT_MINOR" ;;
  major) NEW_TAG="$NEXT_MAJOR" ;;
  v*.*.*) NEW_TAG="$TARGET_TYPE" ;;
  [0-9]*.*.*) NEW_TAG="v$TARGET_TYPE" ;;
esac
if git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
  fatal "Le tag $NEW_TAG existe déjà dans le dépôt."
fi

# 10. Confirmation (an alternative can be typed instead)
echo -e "${BOLD}Tag à créer : ${GREEN}${NEW_TAG}${NC} (${TARGET_TYPE})"
read -rp "Confirmer la création de la release ${NEW_TAG} ? [O/n] (ou tapez une alternative ex: minor, patch, v2.5.1) : " CONFIRM
if [[ -n "$CONFIRM" && ! "$CONFIRM" =~ ^[oOyY]$ ]]; then
  if [[ "$CONFIRM" =~ ^[nN]$ ]]; then
    echo -e "\nRelease annulée."
    exit 0
  fi
  case "$CONFIRM" in
    patch) NEW_TAG="$NEXT_PATCH" ;;
    minor) NEW_TAG="$NEXT_MINOR" ;;
    major) NEW_TAG="$NEXT_MAJOR" ;;
    v*.*.*) NEW_TAG="$CONFIRM" ;;
    [0-9]*.*.*) NEW_TAG="v$CONFIRM" ;;
    *) fatal "Valeur alternative invalide : '$CONFIRM'" ;;
  esac
  if git rev-parse "$NEW_TAG" >/dev/null 2>&1; then
    fatal "Le tag $NEW_TAG existe déjà dans le dépôt."
  fi
  echo -e "Nouveau tag retenu : ${BOLD}${GREEN}${NEW_TAG}${NC}"
fi

# 11. Version of the integration (what Home Assistant shows) and release notes
CLEAN_VER="${NEW_TAG#v}"
info "Mise à jour de la version de ${MANIFEST} vers ${CLEAN_VER}..."
sed -i -E "s/(\"version\": *)\"[^\"]+\"/\1\"$CLEAN_VER\"/" "$MANIFEST"
if ! grep -q "\"version\": *\"$CLEAN_VER\"" "$MANIFEST"; then
  fatal "Échec de la mise à jour de la version dans ${MANIFEST} !"
fi
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$MANIFEST" || fatal "${MANIFEST} n'est plus un JSON valide !"
ok "manifest.json synchronisé (${CLEAN_VER})."

# The "Unreleased" section becomes the one of the release; the next feat/fix entry creates it again.
sed -i "s/^${UNRELEASED}\$/## ${NEW_TAG} ($(date +%F))/" CHANGELOG.md
ok "CHANGELOG.md : section \"Unreleased\" renommée en ${NEW_TAG}."

# 12. Commit and push
info "Commit automatique de la version ${NEW_TAG}..."
git add "$MANIFEST" CHANGELOG.md
git commit -q -m "chore(release): bump integration version to ${NEW_TAG}"
info "Push du commit sur origin/${CURRENT_BRANCH}..."
git push origin "$CURRENT_BRANCH"
ok "Commit de version poussé sur origin."

# 13. Annotated tag, pushed: it triggers the Release workflow
info "Création du tag Git ${NEW_TAG}..."
git tag -a "$NEW_TAG" -m "Release $NEW_TAG"
git push origin "$NEW_TAG"

echo ""
ok "${BOLD}${GREEN}Tag ${NEW_TAG} poussé avec succès sur GitHub !${NC}"
echo -e "${CYAN}Le workflow GitHub Actions « Release » crée la Release GitHub en BROUILLON,${NC}"
echo -e "${CYAN}avec les notes de la section ${NEW_TAG} de CHANGELOG.md.${NC}"
echo ""
echo -e "${YELLOW}Ouvrez ensuite la release en brouillon sur GitHub, ajustez le titre et les notes,${NC}"
echo -e "${YELLOW}puis cliquez sur « Publish release ». Tant qu'elle est en brouillon, HACS ne la voit pas.${NC}"
echo ""
