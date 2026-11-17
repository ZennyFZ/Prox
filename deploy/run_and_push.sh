#!/usr/bin/env bash
# Chay filter_proxies.py tren VPS roi day good_proxies.txt len GitHub.
# Duoc goi boi systemd (deploy/prox-refresh.service). Toan bo logic nam trong
# main() de bash doc het file truoc khi `git reset` co the thay doi chinh no.
set -euo pipefail

main() {
    local repo_dir branch
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    branch="${PROX_BRANCH:-main}"
    cd "$repo_dir"

    # Dong bo code moi nhat (VPS chi la may chay, khong sua code tai day)
    git fetch --quiet origin "$branch"
    git reset --quiet --hard "origin/$branch"

    "$repo_dir/.venv/bin/python" -u filter_proxies.py --out good_proxies.txt

    git add -f -- good_proxies.txt
    if git diff --cached --quiet -- good_proxies.txt; then
        echo "Ket qua khong doi; khong push."
        return 0
    fi

    local count
    count="$(grep -c . good_proxies.txt || true)"
    git commit --quiet -m "chore: refresh working proxy list ($count proxies)"

    local attempt
    for attempt in 1 2 3; do
        if git push --quiet origin "HEAD:$branch"; then
            echo "Da push $count proxies len origin/$branch."
            return 0
        fi
        echo "Push that bai (lan $attempt); rebase len origin/$branch roi thu lai..."
        git pull --quiet --rebase origin "$branch"
        sleep 5
    done
    echo "Push that bai sau 3 lan." >&2
    return 1
}

main "$@"
exit $?
