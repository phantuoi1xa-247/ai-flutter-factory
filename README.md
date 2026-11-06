# AI App Factory – Flutter CI

Repo này được workflow n8n **AI App Factory (Flutter)** dùng để build và kiểm thử app Flutter do AI sinh ra.

- Nhánh `main`: chứa script CI (`.github/workflows/flutter-ci.yml`, `ci/`). Không sửa tay trừ khi cần.
- Nhánh `app/<mã-phiên>`: mã nguồn từng app (mỗi vòng sửa là một commit).
- Nhánh `gh-pages`: bản Flutter Web chạy thử, đường dẫn `/<mã-phiên>/r<vòng>/`.

Mỗi lần chạy, CI thực hiện: `flutter pub get` → `dart format` → `flutter analyze` → `flutter test` → kiểm tra Clean Architecture (`ci/arch_check.py`) → `flutter build web` → đăng lên Pages → gửi báo cáo JSON về n8n.
