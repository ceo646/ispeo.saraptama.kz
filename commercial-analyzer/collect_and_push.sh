#!/usr/bin/env bash
# Один запуск = собрать данные krisha.kz и запушить их в GitHub.
# Для Termux (Android) / iSH (iPhone). Перед первым запуском настройте
# git-доступ (см. README, раздел «Сбор данных с телефона»).
set -e
cd "$(dirname "$0")"

echo "== 1/3: обновляю ветку =="
git pull --rebase origin claude/commercial-property-analysis-5tp9zm || true

echo "== 2/3: собираю данные с krisha.kz =="
python collector.py

echo "== 3/3: пушу данные в GitHub =="
git add data/
git commit -m "data: krisha raw pages $(date +%F)" || {
  echo "Нечего коммитить."; exit 0; }

for i in 1 2 3 4; do
  git push -u origin claude/commercial-property-analysis-5tp9zm && {
    echo "Готово! Напишите Claude в сессии: «данные загружены»."; exit 0; }
  echo "Push не прошёл, повтор через $((2**i)) сек…"; sleep $((2**i))
done
echo "Push не удался. Проверьте интернет и токен в remote URL."; exit 1
