#!/usr/bin/env bash
# Chạy toàn bộ kiểm tra cho app Flutter do AI sinh ra. Không bao giờ dừng giữa chừng:
# mỗi bước ghi log + mã thoát vào thư mục out/, send_report.py sẽ tổng hợp.
set +e
OUT="$GITHUB_WORKSPACE/out"
mkdir -p "$OUT"
cd "$GITHUB_WORKSPACE/app" || exit 0

flutter --version > "$OUT/version.log" 2>&1

# Tạo phần nền tảng (web/, .metadata...) còn thiếu. Không ghi đè file AI đã viết.
git ls-files > "$OUT/tracked.txt"
flutter create . --platforms=web --project-name app --org com.amazinpro > "$OUT/create.log" 2>&1
echo $? > "$OUT/create.code"
# Xoá file mẫu mà flutter create sinh thêm trong lib/, test/ và analysis_options.yaml (nếu AI không viết)
git status --porcelain --untracked-files=all -- lib test analysis_options.yaml 2>/dev/null \
  | awk '$1=="??"{print $2}' | while read -r f; do rm -f "$f"; done

flutter pub get > "$OUT/pub.log" 2>&1
echo $? > "$OUT/pub.code"

dart format --output=none --set-exit-if-changed lib test > "$OUT/format.log" 2>&1
echo $? > "$OUT/format.code"

flutter analyze --no-fatal-infos > "$OUT/analyze.log" 2>&1
echo $? > "$OUT/analyze.code"

flutter test --machine > "$OUT/test.jsonl" 2> "$OUT/test.err"
echo $? > "$OUT/test.code"

python3 "$GITHUB_WORKSPACE/tools/ci/arch_check.py" . > "$OUT/arch.json" 2> "$OUT/arch.err"

flutter build web --release --base-href "/$REPO_NAME/$RUN_KEY/r$ROUND/" > "$OUT/build.log" 2>&1
BUILD=$?
echo $BUILD > "$OUT/build.code"
if [ "$BUILD" -eq 0 ]; then
  echo "build_ok=true" >> "$GITHUB_OUTPUT"
else
  echo "build_ok=false" >> "$GITHUB_OUTPUT"
fi
exit 0
