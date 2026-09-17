'use strict';
// Russian source strings are the translation keys. User data and file paths stay intact.
const translations = {
  "Olzha Agro — мониторинг полей": {
    "en": "Olzha Agro — field monitoring",
    "kk": "Olzha Agro — егістік мониторингі"
  },
  "ЦИФРОВОЕ ЗЕМЛЕДЕЛИЕ": {
    "en": "DIGITAL AGRICULTURE",
    "kk": "ЦИФРЛЫҚ ЕГІНШІЛІК"
  },
  "ОА": {
    "en": "OA",
    "kk": "ОА"
  },
  "Рабочее пространство": {
    "en": "Workspace",
    "kk": "Жұмыс кеңістігі"
  },
  "Мониторинг посевов": {
    "en": "Crop monitoring",
    "kk": "Егістікті бақылау"
  },
  "УПРАВЛЕНИЕ": {
    "en": "MANAGEMENT",
    "kk": "БАСҚАРУ"
  },
  "Обзор полей": {
    "en": "Field overview",
    "kk": "Егістіктерге шолу"
  },
  "Новый анализ": {
    "en": "New analysis",
    "kk": "Жаңа талдау"
  },
  "Выгрузка данных": {
    "en": "Data export",
    "kk": "Деректерді жүктеп алу"
  },
  "Каждый снимок.": {
    "en": "Every image.",
    "kk": "Әрбір сурет."
  },
  "Больше понимания.": {
    "en": "More insight.",
    "kk": "Көбірек түсінік."
  },
  "Наблюдайте за состоянием посевов и проверяйте находки на поле.": {
    "en": "Monitor crop health and check findings in the field.",
    "kk": "Егістіктің жағдайын бақылап, табылған нысандарды тексеріңіз."
  },
  "Локальное пространство": {
    "en": "Local workspace",
    "kk": "Жергілікті жұмыс кеңістігі"
  },
  "АНАЛИТИКА ПОЛЕЙ": {
    "en": "FIELD ANALYTICS",
    "kk": "ЕГІСТІК АНАЛИТИКАСЫ"
  },
  "Поле под наблюдением": {
    "en": "Your field in focus",
    "kk": "Егістік бақылауда"
  },
  "От снимка с дрона — к понятной картине растительности.": {
    "en": "From drone imagery to a clear view of vegetation.",
    "kk": "Дрон суретінен өсімдік жамылғысының анық көрінісіне дейін."
  },
  "＋ Новый анализ": {
    "en": "＋ New analysis",
    "kk": "＋ Жаңа талдау"
  },
  "● ТОЧНОЕ ЗЕМЛЕДЕЛИЕ": {
    "en": "● PRECISION AGRICULTURE",
    "kk": "● ДӘЛМЕ-ДӘЛ ЕГІНШІЛІК"
  },
  "Замечайте больше.": {
    "en": "See more.",
    "kk": "Көбірек байқаңыз."
  },
  "Принимайте решения": {
    "en": "Make decisions",
    "kk": "Шешімдерді"
  },
  "на основе данных.": {
    "en": "based on data.",
    "kk": "деректерге сүйеніп қабылдаңыз."
  },
  "Загрузите фотографии поля, изучите найденные": {
    "en": "Upload field photos, explore detected",
    "kk": "Егістік суреттерін жүктеңіз, табылған"
  },
  "объекты и сохраните результаты для вашей команды.": {
    "en": "objects and save results for your team.",
    "kk": "нысандарды зерттеп, нәтижелерді тобыңыз үшін сақтаңыз."
  },
  "Перейти к анализу": {
    "en": "Start exploring",
    "kk": "Талдауға өту"
  },
  "Область растительности": {
    "en": "Vegetation area",
    "kk": "Өсімдік аймағы"
  },
  "ВЗГЛЯД НА ПОЛЕ СВЕРХУ": {
    "en": "A FIELD VIEW FROM ABOVE",
    "kk": "ЕГІСТІККЕ ЖОҒАРЫДАН КӨЗҚАРАС"
  },
  "Обзор результатов": {
    "en": "Results overview",
    "kk": "Нәтижелерге шолу"
  },
  "Нет завершённых анализов": {
    "en": "No completed analyses",
    "kk": "Аяқталған талдаулар жоқ"
  },
  "Снимков обработано": {
    "en": "Images processed",
    "kk": "Өңделген суреттер"
  },
  "В выбранном анализе": {
    "en": "In the selected analysis",
    "kk": "Таңдалған талдауда"
  },
  "Предполагаемых сорняков": {
    "en": "Suspected weeds",
    "kk": "Болжамды арамшөптер"
  },
  "Объекты с определённым видом": {
    "en": "Objects with an identified species",
    "kk": "Түрі анықталған нысандар"
  },
  "Видов найдено": {
    "en": "Species found",
    "kk": "Табылған түрлер"
  },
  "По эталонным фотографиям": {
    "en": "Based on reference photos",
    "kk": "Эталондық суреттер бойынша"
  },
  "Требуют проверки": {
    "en": "Need review",
    "kk": "Тексеруді қажет етеді"
  },
  "Объекты неизвестного вида": {
    "en": "Objects of unknown species",
    "kk": "Түрі белгісіз нысандар"
  },
  "Состав растительности": {
    "en": "Vegetation composition",
    "kk": "Өсімдік жамылғысының құрамы"
  },
  "По видам": {
    "en": "By species",
    "kk": "Түрлері бойынша"
  },
  "После анализа здесь появится распределение видов.": {
    "en": "Species distribution will appear here after analysis.",
    "kk": "Талдаудан кейін түрлердің үлестірімі осында көрсетіледі."
  },
  "Результаты предварительные и требуют проверки агрономом.": {
    "en": "Results are preliminary and require an agronomist’s review.",
    "kk": "Нәтижелер алдын ала берілген және агрономның тексеруін қажет етеді."
  },
  "Последние анализы": {
    "en": "Recent analyses",
    "kk": "Соңғы талдаулар"
  },
  "ИСТОРИЯ": {
    "en": "HISTORY",
    "kk": "ТАРИХ"
  },
  "Вы ещё не запускали анализ.": {
    "en": "You have not run an analysis yet.",
    "kk": "Сіз әлі талдау жүргізген жоқсыз."
  },
  "Снимки и обнаружения": {
    "en": "Images and detections",
    "kk": "Суреттер мен анықталған нысандар"
  },
  "Нажмите на снимок, чтобы рассмотреть найденные объекты.": {
    "en": "Click an image to inspect detected objects.",
    "kk": "Табылған нысандарды қарау үшін суретті басыңыз."
  },
  "Выгрузить данные ↗": {
    "en": "Export data ↗",
    "kk": "Деректерді жүктеп алу ↗"
  },
  "Здесь начинается наблюдение": {
    "en": "Monitoring starts here",
    "kk": "Бақылау осы жерден басталады"
  },
  "Добавьте первый снимок поля — результаты появятся здесь.": {
    "en": "Add your first field image — results will appear here.",
    "kk": "Егістіктің алғашқы суретін қосыңыз — нәтижелер осында көрсетіледі."
  },
  "Загрузить снимки": {
    "en": "Upload images",
    "kk": "Суреттерді жүктеу"
  },
  "ИССЛЕДОВАНИЕ ПОСЕВОВ": {
    "en": "CROP EXPLORATION",
    "kk": "ЕГІСТІКТІ ЗЕРТТЕУ"
  },
  "Добавьте снимки с дрона. Мы найдём и отметим области растительности.": {
    "en": "Add drone images. We will detect and mark vegetation areas.",
    "kk": "Дрон суреттерін қосыңыз. Біз өсімдік аймақтарын тауып, белгілейміз."
  },
  "Фотографии поля": {
    "en": "Field photos",
    "kk": "Егістік суреттері"
  },
  "Перетащите снимки сюда": {
    "en": "Drop images here",
    "kk": "Суреттерді осында сүйреп әкеліңіз"
  },
  "или нажмите, чтобы выбрать файлы": {
    "en": "or click to choose files",
    "kk": "немесе файлдарды таңдау үшін басыңыз"
  },
  "JPG, PNG · до 20 файлов · до 100 МБ": {
    "en": "JPG, PNG · up to 20 files · up to 100 MB",
    "kk": "JPG, PNG · 20 файлға дейін · 100 МБ-қа дейін"
  },
  "Файлы не выбраны": {
    "en": "No files selected",
    "kk": "Файлдар таңдалмаған"
  },
  "Начать анализ ↗": {
    "en": "Start analysis ↗",
    "kk": "Талдауды бастау ↗"
  },
  "КАК ЭТО РАБОТАЕТ": {
    "en": "HOW IT WORKS",
    "kk": "БҰЛ ҚАЛАЙ ЖҰМЫС ІСТЕЙДІ"
  },
  "Три шага к результату": {
    "en": "Three steps to results",
    "kk": "Нәтижеге үш қадам"
  },
  "Добавьте снимки": {
    "en": "Add images",
    "kk": "Суреттерді қосыңыз"
  },
  "Используйте исходные фотографии поля без уменьшения разрешения.": {
    "en": "Use original field photos at full resolution.",
    "kk": "Егістіктің бастапқы суреттерін ажыратымдылығын төмендетпей пайдаланыңыз."
  },
  "Дождитесь анализа": {
    "en": "Wait for analysis",
    "kk": "Талдауды күтіңіз"
  },
  "Растительность будет сопоставлена с эталонами видов и стадий роста.": {
    "en": "Vegetation will be compared with species and growth-stage references.",
    "kk": "Өсімдіктер түрлер мен өсу кезеңдерінің эталондарымен салыстырылады."
  },
  "Проверьте находки": {
    "en": "Review findings",
    "kk": "Табылған нысандарды тексеріңіз"
  },
  "Изучите рамки на снимках и выгрузите таблицу или JSON.": {
    "en": "Inspect image boxes and export a table or JSON.",
    "kk": "Суреттердегі жақтауларды қарап, кестені немесе JSON файлын жүктеп алыңыз."
  },
  "Перед первым запуском добавьте эталоны:": {
    "en": "Before your first analysis, add reference images:",
    "kk": "Алғашқы іске қосу алдында эталондарды қосыңыз:"
  },
  "ВАШИ ДАННЫЕ": {
    "en": "YOUR DATA",
    "kk": "СІЗДІҢ ДЕРЕКТЕРІҢІЗ"
  },
  "Выгрузка результатов": {
    "en": "Export results",
    "kk": "Нәтижелерді жүктеп алу"
  },
  "Сохраните результаты анализа в удобном формате.": {
    "en": "Save analysis results in a convenient format.",
    "kk": "Талдау нәтижелерін ыңғайлы пішімде сақтаңыз."
  },
  "Выбранный анализ": {
    "en": "Selected analysis",
    "kk": "Таңдалған талдау"
  },
  "Сначала запустите анализ или выберите готовый на странице обзора.": {
    "en": "Run an analysis or select a completed one on the overview page.",
    "kk": "Алдымен талдауды бастаңыз немесе шолу бетінен дайын талдауды таңдаңыз."
  },
  "Выбрать анализ ↗": {
    "en": "Select analysis ↗",
    "kk": "Талдауды таңдау ↗"
  },
  "СТРУКТУРИРОВАННЫЕ ДАННЫЕ": {
    "en": "STRUCTURED DATA",
    "kk": "ҚҰРЫЛЫМДАЛҒАН ДЕРЕКТЕР"
  },
  "Полные результаты: снимки, координаты рамок, виды, стадии роста и сходство с эталонами.": {
    "en": "Full results: images, box coordinates, species, growth stages and reference similarity.",
    "kk": "Толық нәтижелер: суреттер, жақтау координаттары, түрлер, өсу кезеңдері және эталондарға ұқсастық."
  },
  "UTF-8 · для интеграций": {
    "en": "UTF-8 · for integrations",
    "kk": "UTF-8 · интеграциялар үшін"
  },
  "⇩ Скачать JSON": {
    "en": "⇩ Download JSON",
    "kk": "⇩ JSON жүктеп алу"
  },
  "ТАБЛИЦА ОБНАРУЖЕНИЙ": {
    "en": "DETECTIONS TABLE",
    "kk": "АНЫҚТАЛҒАН НЫСАНДАР КЕСТЕСІ"
  },
  "Одна строка на обнаруженный объект. Удобно для фильтрации и дальнейшей работы в Excel.": {
    "en": "One row per detected object. Easy to filter and work with in Excel.",
    "kk": "Әр анықталған нысанға бір жол. Excel-де сүзуге және әрі қарай жұмыс істеуге ыңғайлы."
  },
  "UTF-8 BOM · для Excel": {
    "en": "UTF-8 BOM · for Excel",
    "kk": "UTF-8 BOM · Excel үшін"
  },
  "⇩ Скачать CSV": {
    "en": "⇩ Download CSV",
    "kk": "⇩ CSV жүктеп алу"
  },
  "Предпросмотр данных": {
    "en": "Data preview",
    "kk": "Деректерді алдын ала қарау"
  },
  "0 объектов": {
    "en": "0 objects",
    "kk": "0 нысан"
  },
  "Снимок": {
    "en": "Image",
    "kk": "Сурет"
  },
  "Вид": {
    "en": "Species",
    "kk": "Түр"
  },
  "Стадия": {
    "en": "Stage",
    "kk": "Кезең"
  },
  "Сходство": {
    "en": "Similarity",
    "kk": "Ұқсастық"
  },
  "Координаты рамки": {
    "en": "Box coordinates",
    "kk": "Жақтау координаттары"
  },
  "Пока нет данных для выгрузки.": {
    "en": "No data to export yet.",
    "kk": "Жүктеп алатын деректер әзірге жоқ."
  },
  "Предпросмотр: до 100 объектов. В файл выгружаются все результаты. Сходство с эталоном не является вероятностью.": {
    "en": "Preview: up to 100 objects. Exports include all results. Reference similarity is not a probability.",
    "kk": "Алдын ала қарау: 100 нысанға дейін. Файлға барлық нәтиже жүктеледі. Эталонға ұқсастық ықтималдықты білдірмейді."
  },
  "Забота о поле начинается с наблюдения": {
    "en": "Field care starts with observation",
    "kk": "Егістікке қамқорлық бақылаудан басталады"
  },
  "Мониторинг растительности · MVP": {
    "en": "Vegetation monitoring · MVP",
    "kk": "Өсімдіктер мониторингі · MVP"
  },
  "Рамки обозначают предполагаемые объекты. Проверьте результаты визуально.": {
    "en": "Boxes mark suspected objects. Check the results visually.",
    "kk": "Жақтаулар болжамды нысандарды белгілейді. Нәтижелерді көзбен тексеріңіз."
  },
  "Главное меню": {
    "en": "Main menu",
    "kk": "Басты мәзір"
  },
  "Выберите анализ": {
    "en": "Select an analysis",
    "kk": "Талдауды таңдаңыз"
  },
  "Закрыть": {
    "en": "Close",
    "kk": "Жабу"
  },
  "Снимок с рамками обнаружений": {
    "en": "Image with detection boxes",
    "kk": "Анықтау жақтаулары бар сурет"
  },
  "Ошибка запроса": {
    "en": "Request failed",
    "kk": "Сұрау қатесі"
  },
  "Пока нет определённых видов. Загрузите снимки или выберите другой анализ.": {
    "en": "No species identified yet. Upload images or select another analysis.",
    "kk": "Әзірге анықталған түрлер жоқ. Суреттерді жүктеңіз немесе басқа талдауды таңдаңыз."
  },
  "Анализ": {
    "en": "Analysis",
    "kk": "Талдау"
  },
  "Неизвестный вид": {
    "en": "Unknown species",
    "kk": "Белгісіз түр"
  },
  "Не определена": {
    "en": "Not identified",
    "kk": "Анықталмаған"
  },
  "Нет обнаружений. После завершения анализа файлы доступны даже при отсутствии объектов.": {
    "en": "No detections. Files are available after analysis even if no objects are found.",
    "kk": "Нысандар анықталмады. Талдау аяқталған соң, нысандар болмаса да файлдар қолжетімді болады."
  },
  "Готово": {
    "en": "Done",
    "kk": "Дайын"
  },
  "В работе": {
    "en": "Running",
    "kk": "Орындалуда"
  },
  "Ошибка": {
    "en": "Error",
    "kk": "Қате"
  },
  "Анализ завершился с ошибкой.": {
    "en": "Analysis failed.",
    "kk": "Талдау қатемен аяқталды."
  },
  "Не удалось связаться с сервером.": {
    "en": "Could not connect to the server.",
    "kk": "Серверге қосылу мүмкін болмады."
  },
  "Загрузка снимков…": {
    "en": "Uploading images…",
    "kk": "Суреттер жүктелуде…"
  },
  "Анализ выполняется…": {
    "en": "Analyzing…",
    "kk": "Талдау орындалуда…"
  },
  "Выберите только JPG, JPEG или PNG.": {
    "en": "Select only JPG, JPEG or PNG files.",
    "kk": "Тек JPG, JPEG немесе PNG файлдарын таңдаңыз."
  },
  "За один анализ можно загрузить до 20 файлов общим размером до 99 МБ.": {
    "en": "Upload up to 20 files totaling up to 99 MB per analysis.",
    "kk": "Бір талдау үшін жалпы көлемі 99 МБ-қа дейінгі 20 файлға дейін жүктеуге болады."
  },
  "Результаты из терминала": {
    "en": "Terminal results",
    "kk": "Терминал нәтижелері"
  },
  "найденные объекты": {
    "en": "detected objects",
    "kk": "табылған нысандар"
  },
  "предполагаемых сорняков": {
    "en": "suspected weeds",
    "kk": "болжамды арамшөп"
  },
  "неизвестных": {
    "en": "unknown",
    "kk": "белгісіз"
  },
  "снимков": {
    "en": "images",
    "kk": "сурет"
  },
  "объектов": {
    "en": "objects",
    "kk": "нысан"
  },
  "файлов": {
    "en": "files",
    "kk": "файл"
  },
  "МБ": {
    "en": "MB",
    "kk": "МБ"
  },
  "Удалить": {
    "en": "Remove",
    "kk": "Жою"
  },
  "фото": {
    "en": "photos",
    "kk": "сурет"
  },
  "Сервер перезапущен. Запустите анализ повторно.": {
    "en": "The server restarted. Run the analysis again.",
    "kk": "Сервер қайта іске қосылды. Талдауды қайта бастаңыз."
  },
  "Добавьте эталоны в data/Сорняки/Вид/Стадия, затем повторите запуск.": {
    "en": "Add reference images to data/Сорняки/Вид/Стадия, then try again.",
    "kk": "data/Сорняки/Вид/Стадия ішіне эталондарды қосып, қайта іске қосыңыз."
  },
  "Выберите от 1 до 20 фотографий.": {
    "en": "Select between 1 and 20 photos.",
    "kk": "1–20 сурет таңдаңыз."
  },
  "Допустимы только JPG, JPEG и PNG.": {
    "en": "Only JPG, JPEG and PNG are allowed.",
    "kk": "Тек JPG, JPEG және PNG рұқсат етіледі."
  },
  "Анализ уже выполняется. Дождитесь его завершения.": {
    "en": "An analysis is already running. Wait for it to finish.",
    "kk": "Талдау қазір орындалуда. Оның аяқталуын күтіңіз."
  },
  "Общий размер загрузки должен быть не больше 100 МБ.": {
    "en": "Total upload size must not exceed 100 MB.",
    "kk": "Жүктелетін файлдардың жалпы көлемі 100 МБ-тан аспауы тиіс."
  },
  "Ожидаются фотографии в форме загрузки.": {
    "en": "Expected photos in the upload form.",
    "kk": "Жүктеу пішімінде суреттер күтілуде."
  },
  "Не удалось запустить анализ. Подробности в терминале сервера.": {
    "en": "Could not start analysis. See the server terminal for details.",
    "kk": "Талдауды бастау мүмкін болмады. Толық ақпарат сервер терминалында."
  },
  "Не найдено": {
    "en": "Not found",
    "kk": "Табылмады"
  },
  "Запрос с другого сайта запрещён": {
    "en": "Cross-site request blocked",
    "kk": "Басқа сайттан келген сұрауға тыйым салынған"
  },
  "Некорректный идентификатор анализа": {
    "en": "Invalid analysis ID",
    "kk": "Талдау идентификаторы жарамсыз"
  },
  "Изображение не найдено": {
    "en": "Image not found",
    "kk": "Сурет табылмады"
  },
  "Некорректный путь": {
    "en": "Invalid path",
    "kk": "Жол жарамсыз"
  },
  "Подготовка": {
    "en": "Setup",
    "kk": "Дайындық"
  },
  "ПОДГОТОВКА К РАБОТЕ": {
    "en": "GETTING STARTED",
    "kk": "ЖҰМЫСҚА ДАЙЫНДЫҚ"
  },
  "Эталоны и проверка": {
    "en": "References and checks",
    "kk": "Эталондар мен тексеру"
  },
  "Добавьте образцы растений, затем загрузите снимки поля на вкладке «Новый анализ».": {
    "en": "Add plant references, then upload field images on the New analysis tab.",
    "kk": "Өсімдік үлгілерін қосып, «Жаңа талдау» қойындысында егістік суреттерін жүктеңіз."
  },
  "Добавить эталоны": {
    "en": "Add references",
    "kk": "Эталондарды қосу"
  },
  "Выберите фотографии одного вида на одной стадии роста. Повторите для остальных групп.": {
    "en": "Choose photos of one species at one growth stage. Repeat for other groups.",
    "kk": "Бір түрдің бір өсу кезеңіндегі суреттерін таңдаңыз. Басқа топтар үшін қайталаңыз."
  },
  "Вид растения": {
    "en": "Plant species",
    "kk": "Өсімдік түрі"
  },
  "Стадия роста": {
    "en": "Growth stage",
    "kk": "Өсу кезеңі"
  },
  "Бодяк полевой": {
    "en": "Creeping thistle",
    "kk": "Егістік қалуен"
  },
  "Розетка": {
    "en": "Rosette",
    "kk": "Жапырақ дегелегі"
  },
  "Фотографии эталонов": {
    "en": "Reference photos",
    "kk": "Эталон суреттері"
  },
  "До 20 фотографий за раз, суммарно до 99 МБ.": {
    "en": "Up to 20 photos at a time, up to 99 MB total.",
    "kk": "Бір ретте 20 суретке дейін, жалпы көлемі 99 МБ-қа дейін."
  },
  "Сохранить эталоны": {
    "en": "Save references",
    "kk": "Эталондарды сақтау"
  },
  "Проверка системы": {
    "en": "System check",
    "kk": "Жүйені тексеру"
  },
  "Проверяет компоненты обработки на тестовых изображениях без загрузки модели. Реальную работу модели проверяйте запуском анализа.": {
    "en": "Checks processing components with test images without downloading the model. Run an analysis to test the actual model.",
    "kk": "Модельді жүктемей, өңдеу құрамдастарын сынақ суреттерімен тексереді. Нақты модельді тексеру үшін талдауды іске қосыңыз."
  },
  "Запустить проверку": {
    "en": "Run check",
    "kk": "Тексеруді бастау"
  },
  "Загруженные эталоны": {
    "en": "Uploaded references",
    "kk": "Жүктелген эталондар"
  },
  "Фотографии": {
    "en": "Photos",
    "kk": "Суреттер"
  },
  "Настройки анализа": {
    "en": "Analysis settings",
    "kk": "Талдау параметрлері"
  },
  "Устройство": {
    "en": "Device",
    "kk": "Құрылғы"
  },
  "Автоматически": {
    "en": "Automatic",
    "kk": "Автоматты"
  },
  "Размер тайла": {
    "en": "Tile size",
    "kk": "Тайл өлшемі"
  },
  "Перекрытие тайлов": {
    "en": "Tile overlap",
    "kk": "Тайлдардың қабаттасуы"
  },
  "Порог сходства": {
    "en": "Similarity threshold",
    "kk": "Ұқсастық шегі"
  },
  "Размер пакета": {
    "en": "Batch size",
    "kk": "Пакет өлшемі"
  },
  "Сохранить отладочные изображения": {
    "en": "Save debug images",
    "kk": "Жөндеу суреттерін сақтау"
  },
  "Перед первым запуском добавьте эталоны через сайт.": {
    "en": "Before the first run, add references through the website.",
    "kk": "Алғашқы іске қосу алдында сайт арқылы эталондарды қосыңыз."
  },
  "Журнал анализа": {
    "en": "Analysis log",
    "kk": "Талдау журналы"
  },
  "Анализ для просмотра журнала": {
    "en": "Analysis log selection",
    "kk": "Журналын қарау үшін талдау"
  },
  "Выберите анализ для просмотра журнала.": {
    "en": "Select an analysis to view its log.",
    "kk": "Журналын қарау үшін талдауды таңдаңыз."
  },
  "Снимки и дополнительные файлы": {
    "en": "Images and additional files",
    "kk": "Суреттер мен қосымша файлдар"
  },
  "Архив содержит результаты, снимки с рамками, журнал и отладочные изображения, если они включены.": {
    "en": "The archive includes results, annotated images, the log, and debug images if enabled.",
    "kk": "Мұрағатта нәтижелер, жақтаулары бар суреттер, журнал және қосылған болса, жөндеу суреттері бар."
  },
  "Скачать ZIP": {
    "en": "Download ZIP",
    "kk": "ZIP жүктеп алу"
  },
  "Скачать разметку YOLO": {
    "en": "Download YOLO labels",
    "kk": "YOLO белгілерін жүктеп алу"
  },
  "Разметка YOLO включает совпадения от 0.70. Перед обучением проверьте рамки и разделите данные на обучающую и проверочную выборки. Экспорт доступен для анализов, запущенных через сайт.": {
    "en": "YOLO labels include matches of 0.70 or higher. Review boxes and split training and validation data before training. Available for analyses run through the website.",
    "kk": "YOLO белгілеріне ұқсастығы 0.70 және одан жоғары сәйкестіктер кіреді. Оқыту алдында жақтауларды тексеріп, деректерді оқыту және тексеру жиындарына бөліңіз. Сайтта іске қосылған талдаулар үшін қолжетімді."
  },
  "Пока нет эталонов. Добавьте фотографии выше.": {
    "en": "No references yet. Add photos above.",
    "kk": "Эталондар әзірге жоқ. Жоғарыда суреттерді қосыңыз."
  },
  "Проверка ещё не запускалась.": {
    "en": "No check has been run yet.",
    "kk": "Тексеру әлі іске қосылған жоқ."
  },
  "Проверка выполняется…": {
    "en": "Checking…",
    "kk": "Тексеру орындалуда…"
  },
  "Проверка пройдена.": {
    "en": "Check passed.",
    "kk": "Тексеру сәтті өтті."
  },
  "Проверка выявила ошибки. Подробности ниже.": {
    "en": "The check found errors. See details below.",
    "kk": "Тексеру қателерді анықтады. Толық ақпарат төменде."
  },
  "Сохранение…": {
    "en": "Saving…",
    "kk": "Сақталуда…"
  },
  "Эталоны сохранены. Можно запускать анализ.": {
    "en": "References saved. You can start an analysis.",
    "kk": "Эталондар сақталды. Талдауды бастауға болады."
  },
  "Нет анализов": {
    "en": "No analyses",
    "kk": "Талдаулар жоқ"
  },
  "Журнал пока пуст.": {
    "en": "The log is empty.",
    "kk": "Журнал әзірге бос."
  },
  "Добавьте эталоны на вкладке «Подготовка», затем повторите запуск.": {
    "en": "Add references on the Setup tab, then try again.",
    "kk": "«Дайындық» қойындысында эталондарды қосып, қайта іске қосыңыз."
  },
  "Укажите вид и стадию без слешей, до 100 символов.": {
    "en": "Enter species and stage without slashes, up to 100 characters.",
    "kk": "Түрі мен кезеңін қиғаш сызықсыз, 100 таңбаға дейін енгізіңіз."
  },
  "Некорректное устройство обработки.": {
    "en": "Invalid processing device.",
    "kk": "Өңдеу құрылғысы жарамсыз."
  },
  "Проверьте числовые настройки анализа.": {
    "en": "Check the numeric analysis settings.",
    "kk": "Талдаудың сандық параметрлерін тексеріңіз."
  },
  "Настройки анализа выходят за допустимые пределы.": {
    "en": "Analysis settings are outside the allowed range.",
    "kk": "Талдау параметрлері рұқсат етілген шектен тыс."
  },
  "Сначала дождитесь завершения анализа.": {
    "en": "Wait for the analysis to finish first.",
    "kk": "Алдымен талдаудың аяқталуын күтіңіз."
  },
  "Для экспорта YOLO запустите анализ через сайт.": {
    "en": "Run an analysis through the website to export YOLO labels.",
    "kk": "YOLO белгілерін жүктеп алу үшін талдауды сайт арқылы іске қосыңыз."
  },
  "Не удалось выполнить действие. Проверьте систему на вкладке «Подготовка».": {
    "en": "Could not complete the action. Run a system check on the Setup tab.",
    "kk": "Әрекет орындалмады. «Дайындық» қойындысында жүйені тексеріңіз."
  },
  "Нет подходящих обнаружений для разметки YOLO.": {
    "en": "No detections qualify for YOLO labels.",
    "kk": "YOLO белгілеріне жарамды нысандар анықталмады."
  },
  "Пробное обучение YOLO": {
    "en": "YOLO trial training",
    "kk": "YOLO сынақ оқытуы"
  },
  "5 эпох, размер 320, пакет 4. Датасет: 59 обучающих и 20 проверочных тайлов из автоматической разметки. Один класс отсутствует в обучающей выборке. Это эксперимент, а не проверенная модель.": {
    "en": "5 epochs, image size 320, batch 4. Dataset: 59 training and 20 validation tiles with automatic labels. One class is missing from training. This is an experiment, not a validated model.",
    "kk": "5 эпоха, өлшемі 320, пакет 4. Датасет: автоматты белгіленген 59 оқыту және 20 тексеру тайлы. Оқыту жиынында бір класс жоқ. Бұл тексерілген модель емес, тәжірибе."
  },
  "Запустить пробное обучение": {
    "en": "Start trial training",
    "kk": "Сынақ оқытуын бастау"
  },
  "Скачать веса YOLO": {
    "en": "Download YOLO weights",
    "kk": "YOLO салмақтарын жүктеп алу"
  },
  "Прогресс обучения": {
    "en": "Training progress",
    "kk": "Оқыту барысы"
  },
  "Обучение ещё не запускалось.": {
    "en": "Training has not started yet.",
    "kk": "Оқыту әлі басталған жоқ."
  },
  "Обучение выполняется…": {
    "en": "Training…",
    "kk": "Оқыту орындалуда…"
  },
  "Пробное обучение завершено.": {
    "en": "Trial training completed.",
    "kk": "Сынақ оқытуы аяқталды."
  },
  "Обучение завершилось с ошибкой.": {
    "en": "Training failed.",
    "kk": "Оқыту қатемен аяқталды."
  },
  "Обучение остановлено. Можно запустить повторно.": {
    "en": "Training stopped. You can start it again.",
    "kk": "Оқыту тоқтады. Қайта бастауға болады."
  },
  "Обучение уже выполняется.": {
    "en": "Training is already running.",
    "kk": "Оқыту қазір орындалуда."
  },
  "Не найден подготовленный датасет YOLO.": {
    "en": "Prepared YOLO dataset not found.",
    "kk": "Дайындалған YOLO датасеті табылмады."
  },
  "Не найдены исходные веса YOLO11n.": {
    "en": "Initial YOLO11n weights not found.",
    "kk": "YOLO11n бастапқы салмақтары табылмады."
  },
  "Веса ещё не сохранены.": {
    "en": "Weights have not been saved yet.",
    "kk": "Салмақтар әлі сақталмаған."
  },
  "A · Двудольные (широколистные)": {
    "en": "A · Broadleaf weeds",
    "kk": "A · Қосжарнақты (жалпақ жапырақты)"
  },
  "B · Злаковые (узколистные)": {
    "en": "B · Grass weeds",
    "kk": "B · Астық тұқымдас (жіңішке жапырақты)"
  },
  "Приоритет: многолетник": {
    "en": "Priority: perennial",
    "kk": "Басымдық: көпжылдық арамшөп"
  },
  "Идеальное окно: базовая/минимальная норма по регламенту препарата": {
    "en": "Ideal window: base/minimum rate per product label",
    "kk": "Қолайлы кезең: препарат нұсқаулығына сай негізгі/ең аз мөлшер"
  },
  "4–6 листьев: по заданному правилу +15–20%; требуется проверка регламента препарата": {
    "en": "4–6 leaves: proposed +15–20% under the supplied rule; check the product label",
    "kk": "4–6 жапырақ: берілген ереже бойынша +15–20%; препарат нұсқаулығын тексеру қажет"
  },
  "Поздняя фаза: возможна неэффективность обработки и повреждение культуры": {
    "en": "Late stage: treatment may be ineffective and damage the crop",
    "kk": "Кеш кезең: өңдеу тиімсіз болып, дақылға зиян келтіруі мүмкін"
  },
  "Фаза не определена: требуется проверка": {
    "en": "Unknown growth stage: review required",
    "kk": "Даму кезеңі анықталмады: тексеру қажет"
  },
  "Не опрыскивать: ниже экономического порога": {
    "en": "Do not spray: below the economic threshold",
    "kk": "Бүрікпеңіз: экономикалық шектен төмен"
  },
  "Стандартная норма по регламенту препарата": {
    "en": "Standard rate per product label",
    "kk": "Препарат нұсқаулығына сай қалыпты мөлшер"
  },
  "Максимальная разрешённая норма по регламенту препарата": {
    "en": "Maximum permitted rate per product label",
    "kk": "Препарат нұсқаулығына сай ең жоғары рұқсат етілген мөлшер"
  },
  "Критическая угроза: срочно оценить обработку": {
    "en": "Critical threat: urgently assess treatment",
    "kk": "Қауіп жоғары: өңдеу қажеттілігін шұғыл бағалау"
  },
  "Требуется проверка агрономом": {
    "en": "Agronomist review required",
    "kk": "Агрономның тексеруі қажет"
  },
  "По заданным порогам": {
    "en": "Under the supplied thresholds",
    "kk": "Берілген шектер бойынша"
  },
  "Решение": {
    "en": "Decision",
    "kk": "Шешім"
  },
  "Есть объекты с неопределённым классом": {
    "en": "Some objects have an unknown class",
    "kk": "Кейбір нысандардың класы анықталмаған"
  },
  "Есть многолетники ниже критического порога: требуется отдельная оценка": {
    "en": "Perennials below the critical threshold need separate assessment",
    "kk": "Көпжылдық арамшөптер қауіпті шектен төмен: бөлек бағалау қажет"
  },
  "Обработка кадра": {
    "en": "Frame processing",
    "kk": "Кадрды өңдеу"
  },
  "Путь за обработку при 20 км/ч": {
    "en": "Distance travelled during processing at 20 km/h",
    "kk": "20 км/сағ жылдамдықта өңдеу кезінде жүрілген жол"
  },
  "с": {
    "en": "s",
    "kk": "с"
  },
  "м": {
    "en": "m",
    "kk": "м"
  },
  "Малолетние": {
    "en": "Annual/biennial weeds",
    "kk": "Бір/екіжылдық арамшөптер"
  },
  "Многолетние": {
    "en": "Perennial weeds",
    "kk": "Көпжылдық арамшөптер"
  },
  "Нужен масштаб": {
    "en": "Scale required",
    "kk": "Масштаб қажет"
  },
  "Анализ выполняется локально. Загрузка модели из интернета возможна только при включённом разрешении. Результаты появятся автоматически.": {
    "en": "Analysis runs locally. Model downloads require explicit permission. Results will appear automatically.",
    "kk": "Талдау жергілікті орындалады. Модельді интернеттен жүктеу үшін рұқсат қажет. Нәтижелер автоматты түрде көрсетіледі."
  }
};
let language = 'ru';
try { language = localStorage.getItem('olzha-language') || 'ru'; } catch (_) {}
if (!['ru', 'en', 'kk'].includes(language)) language = 'ru';
const locale = () => ({ru:'ru-RU', en:'en-US', kk:'kk-KZ'}[language]);
const t = text => translations[text]?.[language] || text;
const staticText = [];
const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
while (walker.nextNode()) {
  const node = walker.currentNode;
  if (node.parentElement.closest('script, style, code')) continue;
  if (translations[node.textContent.trim()]) staticText.push([node, node.textContent]);
}
const staticAttributes = [];
document.querySelectorAll('[aria-label], [alt], [placeholder]').forEach(element => {
  ['aria-label', 'alt', 'placeholder'].forEach(attribute => {
    if (element.hasAttribute(attribute)) staticAttributes.push([element, attribute, element.getAttribute(attribute)]);
  });
});
function translatePage() {
  document.documentElement.lang = language;
  staticText.forEach(([node, source]) => { node.textContent = source.replace(source.trim(), t(source.trim())); });
  staticAttributes.forEach(([element, attribute, source]) => element.setAttribute(attribute, t(source)));
  document.querySelectorAll('[data-language]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.language === language));
  });
}
function jobName(job) {
  const match = /^Анализ · (\d+) фото$/.exec(job.name);
  return match ? `${t('Анализ')} · ${Number(match[1]).toLocaleString(locale())} ${t('фото')}` : t(job.name);
}
translatePage();

function translateMessage(message) {
  // Reverse known translations when an already visible message changes language.
  for (const [source, variants] of Object.entries(translations)) {
    if (message === source || Object.values(variants).includes(message)) return t(source);
  }
  return message;
}
