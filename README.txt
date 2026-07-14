scan_split — разбивка PDF и переименование комплектов

Как пользоваться
----------------
1) Разбить большой скан по титульникам
   Перетащите PDF на run_split.bat
   Результат: папка *_split рядом с исходником
   Файлы: 1.pdf, 2.pdf, 3.pdf ...

2) Переименовать комплекты по номеру и названию
   Перетащите папку *_split на run_rename.bat
   Файлы станут вида:
     1360.443291.2002 Поддон шасси ВЧ-генератора.pdf

Состав папки
------------
  split_pdf_by_titul.exe    - разбивка
  run_split.bat             - запуск разбивки (файл)
  rename_pdfs_by_titul.exe  - переименование
  run_rename.bat            - запуск переименования (папка)
  tesseract\                - OCR (не удалять)

Требования
----------
  Windows 10/11, 64-bit
  Python НЕ нужен
  Отдельная установка Tesseract НЕ нужна

Опции командной строки
----------------------
  split_pdf_by_titul.exe file.pdf --preview
  rename_pdfs_by_titul.exe "C:\path\to\folder" --dry-run
  rename_pdfs_by_titul.exe "C:\path\to\folder" --dpi 250
