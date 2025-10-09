#!/bin/bash
# Usage: ./push_to_github.sh <remote-url>
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <git-remote-url>"
  exit 1
fi
remote="$1"
if [ ! -d .git ]; then
  git init
  git add .
  git commit -m "Initial commit: PT multi-container scripts and Dockerfiles"
fi
git remote remove origin 2>/dev/null || true
git remote add origin "$remote"
git branch -M main || true
git push -u origin main
echo "Pushed to $remote" 
