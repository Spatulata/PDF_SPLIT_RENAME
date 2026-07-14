scan_split — portable (одна папка)

Использование
-------------
1. Перетащи PDF на run_split.bat
   → рядом появится папка *_split с файлами 1.pdf 2.pdf ...

2. Перетащи эту папку на run_rename.bat
   → имена станут:
     1360.443291.2002 Поддон шасси ВЧ-генератора.pdf

Состав (всё здесь)
------------------
  run_split.bat / split_pdf_by_titul.exe     разбивка
  run_rename.bat / rename_pdfs_by_titul.exe  переименование
  tesseract\                                 OCR (не удалять)

  Исходники и сборка (если нужно пересобрать exe):
  *.py  *.spec  requirements*.txt  build_windows.bat

Сборка exe (Windows + Python)
-----------------------------
  build_windows.bat

  Рекомендуется любой Python 3.11+ (в т.ч. 3.14).
  Если exe падает с ошибкой PIL\_avif — удалите .venv и пересоберите.

  Готовые exe копируются в корень этой папки.

Если exe сразу закрывается
--------------------------
  Ошибка: Failed to extract PIL\_avif...
  Это не проблема Python 3.14 — в exe попал лишний модуль Pillow (AVIF).
  1. Удалите папку .venv
  2. Запустите build_windows.bat снова (исправленная сборка без AVIF)
  3. Запускайте run_split.bat / run_rename.bat из корня папки

Требования к запуску
--------------------
  Windows 10/11 x64
  Python НЕ нужен
  Tesseract ставить отдельно НЕ нужно
