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

  Готовые exe сразу копируются в эту же папку.

Требования к запуску
--------------------
  Windows 10/11 x64
  Python НЕ нужен
  Tesseract ставить отдельно НЕ нужно
