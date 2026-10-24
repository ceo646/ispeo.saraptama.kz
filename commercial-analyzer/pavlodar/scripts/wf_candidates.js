export const meta = {
  name: 'pavlodar-candidate-check',
  description: 'Two independent checks per top sale listing: what is really sold, and what rent is realistic',
  phases: [
    { title: 'Object', detail: 'read the full card and check the object on the web' },
    { title: 'Rent', detail: 'realistic rent and yield from comparables' },
  ],
}

const FILE = args.file
const IDS = args.ids

const OBJ = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    what_is_sold: { type: 'string', description: 'что реально продаётся: встроенное помещение, этаж, здание целиком, доля, бизнес, павильон и т.д.' },
    floor_and_access: { type: 'string', description: 'этаж, цоколь/подвал (если есть — обязательно), отдельный вход, линия' },
    condition: { type: 'string' },
    tenant_in_place: { type: 'string', description: 'есть ли арендатор и заявленный арендный доход (цифры из объявления), иначе "нет данных"' },
    price_includes_business_or_land: { type: 'string' },
    red_flags: { type: 'array', items: { type: 'string' } },
    location_note: { type: 'string', description: 'что вокруг адреса (2ГИС/карты/новости): трафик, соседи, ремонт улицы' },
    still_listed: { type: 'string', enum: ['yes', 'no', 'unknown'] },
    verdict: { type: 'string', enum: ['clean', 'caution', 'reject'] },
    verdict_reason: { type: 'string' },
  },
  required: ['id', 'what_is_sold', 'floor_and_access', 'condition', 'tenant_in_place', 'price_includes_business_or_land', 'red_flags', 'location_note', 'still_listed', 'verdict', 'verdict_reason'],
}

const RENT = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    realistic_rent_per_m2: { type: 'number', description: '₸/м² в месяц для ВСЕГО объекта, реалистичная запрашиваемая ставка' },
    rent_low: { type: 'number' },
    rent_high: { type: 'number' },
    vacancy_months_per_year: { type: 'number', description: 'ожидаемый простой, месяцев в год' },
    gross_yield: { type: 'number', description: 'реалистичная валовая доходность, доля (0.11 = 11%)' },
    net_yield: { type: 'number', description: 'после простоя и расходов собственника (налог, ремонт, управление), доля' },
    comps_quality: { type: 'string', enum: ['good', 'fair', 'poor'] },
    reasoning: { type: 'string' },
  },
  required: ['id', 'realistic_rent_per_m2', 'rent_low', 'rent_high', 'vacancy_months_per_year', 'gross_yield', 'net_yield', 'comps_quality', 'reasoning'],
}

const tools = 'Загрузи WebSearch и WebFetch через ToolSearch ("select:WebSearch,WebFetch"). Не обходи капчи и защиты; русская страница krisha /a/show/<id> отдаёт скриптам код 468 — открывай казахскую https://krisha.kz/kz/a/show/<id> через WebFetch, а если и она недоступна, работай по данным из файла. Если лимит поиска исчерпан — опирайся на файл и на то, что откроется через WebFetch, и скажи об этом.'

const objPrompt = id => `Ты проверяешь объявление о продаже коммерческой недвижимости в Павлодаре как скептичный покупатель-инвестор, который хочет сдавать объект в аренду. Прочитай файл ${FILE} (инструмент Read) и найди объект с id ${id}: там полный текст объявления (description), атрибуты на казахском (fields_kz: com.location — где находится, flat.floor — этаж, com.renovation — ремонт, com.location_line — линия: бірінші = первая, аулада = во дворе; com.entrance_opts — вход: бөлек = отдельный, ортақ = общий, көшеден = с улицы), цена и площадь. ${tools}
Задача: понять, ЧТО РЕАЛЬНО продаётся и есть ли подвохи. Обязательно отметь: цоколь или подвал (мы такие не рассматриваем — тогда verdict reject), продажа доли, бизнеса вместе с помещением, земли, требуется ли капремонт, это здание целиком, которому нужно много арендаторов, есть ли действующий арендатор и заявленный доход, нет ли признаков дубля/устаревшего объявления. Посмотри адрес в открытых источниках (2ГИС-выдача в поиске, новости о ремонте улицы, соседние объекты), чтобы описать окружение. verdict: clean — обычное помещение без явных проблем; caution — можно рассматривать, но есть существенные оговорки; reject — не стоит включать в список (цоколь, не помещение, явная ошибка в цене, нет документов, продано и т.п.).`

const rentPrompt = id => `Ты — оценщик арендных ставок коммерческой недвижимости в Павлодаре. Прочитай файл ${FILE} (инструмент Read), объект с id ${id}. Там: площадь, цена, наша оценка ставки (our_estimate), медианы зоны (zone_stats) и список аналогов из объявлений аренды krisha рядом (comps: адрес, площадь, ставка ₸/м² в месяц, расстояние). ${tools}
Задача: независимо оценить, по какой ставке реально сдать ВЕСЬ этот объект (₸/м² в месяц), учитывая: большие площади сдаются дешевле за м² или требуют дробления; первый этаж/линия/вход; тип (офис, торговля, свободное назначение); качество аналогов (они тоже запрашиваемые цены). Можешь проверить ставки по похожим объектам на krisha (казахская версия страниц выдачи https://krisha.kz/arenda/kommercheskaya-nedvizhimost/pavlodar/?_txt_=<улица>), OLX и в 2ГИС. Посчитай: валовую доходность = ставка × площадь × 12 / цена; чистую — с учётом простоя (месяцев в год) и расходов собственника (налог на имущество, текущий ремонт, управление; если не уверен — 8–12% от арендного дохода). Будь консервативен: если аналоги плохие, скажи об этом и сузь оценку.`

phase('Object')
const res = await pipeline(
  IDS,
  id => parallel([
    () => agent(objPrompt(id), { label: `object:${id}`, phase: 'Object', schema: OBJ, effort: 'high' }),
    () => agent(rentPrompt(id), { label: `rent:${id}`, phase: 'Rent', schema: RENT, effort: 'high' }),
  ]).then(([o, r]) => ({ id, object: o, rent: r })),
)
return res.filter(Boolean)
