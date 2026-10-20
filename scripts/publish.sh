#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
account=$(gh api user --jq .login)
repository="hutko-2006-independent-reconstruction"
export GIT_DIR="$PWD/.git-project"
export GIT_WORK_TREE="$PWD"
if [[ ! -f "$GIT_DIR/HEAD" ]]; then
  git init --initial-branch=main
  git config user.name "$account"
  git config user.email "$account@users.noreply.github.com"
fi
git add README.md .gitignore requirements.txt config.json receiver_splitting.json rebuild.sh scripts report figures data logs usage.tex usage.pdf references/README.md references/AGENTS.md references/academic-style.md
git diff --cached --quiet || git commit -m 'Independent public-archive Cocos Plate migration, figures, validation and report'
if gh repo view "$account/$repository" > /dev/null 2>&1; then
  repository="$repository-$(date -u +%Y%m%d-%H%M%S)"
fi
gh repo create "$account/$repository" --public --description 'Independent Python reanalysis of Hutko et al. 2006 with historical and expanded public-archive data; candid partial-reproduction report'
url="git@github.com:$account/$repository.git"
if git remote get-url origin > /dev/null 2>&1; then
  git remote set-url origin "$url"
else
  git remote add origin "$url"
fi
if ! GIT_SSH_COMMAND="ssh -o UserKnownHostsFile=$PWD/.config/known_hosts -o StrictHostKeyChecking=accept-new" git push -u origin main; then
  # gh's existing token can authenticate HTTPS without writing a global helper
  # or placing a token in a URL, shell argument, or committed configuration.
  git remote set-url origin "https://github.com/$account/$repository.git"
  git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin main
fi
printf 'https://github.com/%s/%s\nhttps://github.com/%s/%s/blob/main/report/report.pdf\n' "$account" "$repository" "$account" "$repository"
