import random

START_TIME = 6 * 60   # 6:00
END_TIME   = 27 * 60  # 3:00 (следующего дня)
TOTAL_TIME = END_TIME - START_TIME  # 21 час

# Пиковые интервалы (7-9 и 17-19 ч)
PEAK_TIMES = [(7 * 60, 9 * 60), (17 * 60, 19 * 60)]

BASE_BUSES = 8

# Штрафы
PENALTY_NO_LUNCH_A    = 10  # Отсутствие обеда (1ч) при работе >4ч у водителя А
PENALTY_OVERTIME_A    = 20  # Переработка у А свыше 9 ч
PENALTY_B_SHORT_BREAK = 10  # Отсутствие короткого перерыва каждые 2 ч для B
PENALTY_B_LONG_BREAK  = 15  # Если у B подряд >2 коротких перерыва (нужен длинный ≥60 мин)
PENALTY_TOO_MANY_BUSES= 5   # За использование автобусов с номером свыше BASE_BUSES
PENALTY_BUS_CONFLICT  = 5   # Если одновременно в одну минуту используется >8 автобусов
PENALTY_OVERTIME_B    = 25  # За переработку свыше 12ч у B
PENALTY_B_NO_2DAY_REST= 50  # Если водитель B не отдыхает 2 суток подряд (сутки через двое)
PENALTY_SHIFT_CHANGE  = 5   # Если пересменка между водителями <10 минут на одном автобусе

# Параметры генетического алгоритма
POP_SIZE       = 100
GENERATIONS    = 500
CROSSOVER_PROB = 0.9
MUTATION_PROB  = 0.001

# Коэффициенты фитнес-функции
ALPHA = 10.0           # Важность максимизации количества рейсов
BETA  = 0.5            # Важность минимизации числа водителей
PEAK_BONUS_FACTOR = 0.1# Бонусный множитель за рейсы в пиковое время

DAYS = 7
DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг",
             "Пятница",    "Суббота",  "Воскресенье"]


# ГЕНЕРАЦИЯ ВОЗМОЖНЫХ РЕЙСОВ
def generate_possible_trips():
    """
    Генерируем все потенциальные рейсы на 7 дней.
    Каждый рейс длится 1ч ± 10 мин (50..70).
    Расписание строим пока есть место в интервале с 6:00 до 3:00 (21 час).
    """
    trips = []
    trip_id = 1
    for day in range(DAYS):
        start = 0
        while True:
            route_time = random.randint(50, 70)  # Случайная длительность 50..70 мин
            if start + route_time <= TOTAL_TIME:
                trips.append({
                    'id': trip_id,
                    'day': day,
                    'start_min': START_TIME + start,  # Абсолютное время начала (в минутах от 00:00)
                    'end_min':   START_TIME + start + route_time,
                    'duration':  route_time
                })
                trip_id += 1
                start += route_time
            else:
                break
    return trips

POSSIBLE_TRIPS = generate_possible_trips()

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
def format_time(m):
    """
    Перевод минут от начала суток в строку вида ЧЧ:ММ (24-часовой формат).
    """
    h = (m // 60) % 24
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

def is_peak(minute_of_day):
    """
    Проверяет, попадает ли minute_of_day в пиковый интервал (7-9 или 17-19).
    Используется при подсчёте бонуса в фитнес-функции.
    """
    for (sp, ep) in PEAK_TIMES:
        if sp <= minute_of_day < ep:
            return True
    return False

def random_driver_assignment():
    """
    Случайное назначение водителя.
    20% - водитель не назначается (None, None).
    Иначе 70% - тип 'A', 30% - тип 'B'.
    Возвращаем кортеж (dt, did).
    """
    if random.random() < 0.2:
        return None, None
    dt = random.choices(['A','B'], weights=[70,30], k=1)[0]
    did = random.randint(1,30)
    return dt, did

def random_bus_assignment():
    """
    Случайное назначение автобуса.
    20% шанс вернуть None (автобус не назначается),
    иначе номер автобуса в диапазоне 1..12.
    """
    if random.random() < 0.2:
        return None
    return random.randint(1,12)

# ИНИЦИАЛИЗАЦИЯ ОДНОГО ИНДИВИДУУМА ДЛЯ ГА
def init_individual():
    """
    Каждый ген представляет собой: (trip_id, dt, did, b).
    - trip_id: идентификатор рейса
    - dt, did: тип и ID водителя
    - b: номер автобуса
    С вероятностью 20% рейс пропускаем (назначаем None).
    """
    individual = []
    for trip in POSSIBLE_TRIPS:
        trip_id = trip['id']
        # 20% вероятность пропустить рейс
        if random.random() < 0.2:
            individual.append((trip_id, None, None, None))
        else:
            dt, did = random_driver_assignment()
            b = random_bus_assignment()
            if dt is None or b is None:
                individual.append((trip_id, None, None, None))
            else:
                individual.append((trip_id, dt, did, b))
    return individual

# ДЕКОДИРОВАНИЕ ИНДИВИДУУМА
def decode_individual(ind):
    """
    Превращаем список генов (trip_id, dt, did, b) обратно в расписание.
    Расписание: list из (trip_dict, dt, did, b).
    trip_dict берём из POSSIBLE_TRIPS по trip_id.
    """
    trip_map = {trip['id']: trip for trip in POSSIBLE_TRIPS}
    schedule = []
    for gene in ind:
        trip_id, dt, did, b = gene
        trip = trip_map[trip_id]
        schedule.append((trip, dt, did, b))
    return schedule

# ПРОВЕРКА ОГРАНИЧЕНИЙ И ШТРАФЫ
def check_driver_constraints(schedule):
    """
    Считает штрафы за нарушения графиков водителей (A и B).
    - Тип А: свыше 9ч суммарно (OVERTIME), отсутствие обеда после 4ч без перерыва ≥60мин.
    - Тип B: свыше 12ч (720 мин), каждые 2ч нужен короткий перерыв 15..20мин,
      не более 2 коротких подряд -> нужен ≥60мин,
      "сутки через двое" - штраф (PENALTY_B_NO_2DAY_REST), если B работает в смежные дни (d+1, d+2).
    """
    drivers_map = {}
    for (t, dt, did, b) in schedule:
        # Трекер для каждого (dt, did), собираем их рейсы
        if dt is not None and did is not None and b is not None:
            key = (dt, did)
            if key not in drivers_map:
                drivers_map[key] = []
            drivers_map[key].append(t)

    penalties = 0

    for drv_key, trips in drivers_map.items():
        dt, did = drv_key
        # Сортируем рейсы по дню и времени начала, чтобы анализировать суммарно
        trips.sort(key=lambda x: (x['day'], x['start_min']))
        trips_by_day = {}
        for tr in trips:
            day = tr['day']
            if day not in trips_by_day:
                trips_by_day[day] = []
            trips_by_day[day].append(tr)

        # Штраф за отсутствие "сутки через двое" у B (если появляются в d, d+1 или d+2)
        if dt == 'B':
            used_days = sorted(trips_by_day.keys())
            for d in used_days:
                # если водитель B есть в day d, штрафуем если он же в day d+1 или d+2
                if (d+1 in used_days) or (d+2 in used_days):
                    penalties += PENALTY_B_NO_2DAY_REST

        # Для каждого дня считаем суммарную работу и перерывы
        for day, day_trips in trips_by_day.items():
            total_work = sum(tr['duration'] for tr in day_trips)
            intervals = []
            for i in range(len(day_trips)-1):
                gap = day_trips[i+1]['start_min'] - day_trips[i]['end_min']
                intervals.append(gap)

            if dt == 'A':
                # Проверка на переработку (>9ч)
                if total_work > 540:  # 9ч = 540 мин
                    penalties += PENALTY_OVERTIME_A
                # Проверка на обед (если суммарная работа >4ч, но нет перерыва >=60мин)
                if total_work > 240:  # 4ч = 240 мин
                    had_lunch = False
                    running_time = 0
                    for i, g in enumerate(intervals):
                        running_time += day_trips[i]['duration']
                        if running_time >= 240 and g >= 60:
                            had_lunch = True
                            break
                    if not had_lunch:
                        penalties += PENALTY_NO_LUNCH_A

            if dt == 'B':
                # Проверка на >12ч
                if total_work > 720:
                    penalties += PENALTY_OVERTIME_B
                # Каждые 2ч нужен короткий перерыв >=15мин (или >=60мин каждые 2 коротких)
                work_acc = 0
                short_break_count = 0
                for i in range(len(day_trips)-1):
                    work_acc += day_trips[i]['duration']
                    gap = intervals[i]
                    if work_acc >= 120:  # 2 часа = 120 мин
                        if gap < 15:
                            penalties += PENALTY_B_SHORT_BREAK
                        else:
                            if gap < 60:
                                short_break_count += 1
                                if short_break_count > 2:
                                    penalties += PENALTY_B_LONG_BREAK
                            else:
                                short_break_count = 0
                        work_acc = 0
                # В конце дня, если остался незакрытый блок >=2ч
                if work_acc >= 120:
                    penalties += PENALTY_B_SHORT_BREAK

    return penalties

def check_bus_constraints(schedule):
    """
    Подсчитываем, сколько автобусов используется в каждую минуту рабочего окна.
    Если одновременно (в одну минуту) задействовано >BASE_BUSES, начисляем штраф.
    """
    usage = [0]*(TOTAL_TIME+1)
    for (t, dt, did, b) in schedule:
        if b is None or dt is None or did is None:
            continue
        start_i = t['start_min'] - START_TIME
        end_i   = t['end_min']   - START_TIME
        for m in range(start_i, end_i):
            if 0 <= m < TOTAL_TIME:
                usage[m] += 1
    penalties = 0
    for x in usage:
        if x > BASE_BUSES:
            penalties += (x - BASE_BUSES)*PENALTY_BUS_CONFLICT
    return penalties

def check_shift_change(schedule):
    """
    Штраф за пересменку <10 минут (PENALTY_SHIFT_CHANGE).
    Если на одном автобусе подряд идут разные водители (dt,did),
    но между рейсами меньше 10 мин, добавляем штраф.
    """
    bus_map = {}
    for (t, dt, did, b) in schedule:
        if b is not None and dt is not None and did is not None:
            if b not in bus_map:
                bus_map[b] = []
            bus_map[b].append((t, dt, did))

    penalty = 0
    for bus, bus_trips in bus_map.items():
        # Сортируем по (day, start_min)
        bus_trips.sort(key=lambda x: (x[0]['day'], x[0]['start_min']))
        for i in range(len(bus_trips)-1):
            (t1, dt1, did1) = bus_trips[i]
            (t2, dt2, did2) = bus_trips[i+1]
            # Если смена водителя
            if (dt1, did1) != (dt2, did2):
                gap = t2['start_min'] - t1['end_min']
                if gap < 10:
                    penalty += PENALTY_SHIFT_CHANGE
    return penalty

# МЕТРИКИ РАСПИСАНИЯ
def count_buses_used(schedule):
    """
    Вычисляем, какие номера автобусов назначены (b).
    Дополнительно считаем, если max(b) > BASE_BUSES => штраф (доп. автобусы).
    """
    b_set = set(b for (t, dt, did, b) in schedule
                if b is not None and dt is not None and did is not None)
    if not b_set:
        return 0
    max_bus = max(b_set)
    extra = max(0, max_bus - BASE_BUSES)  # Сколько автобусов свыше 8
    return extra

def count_unique_drivers(schedule):
    """
    Кол-во уникальных (dt, did) сочетаний.
    Чем меньше водителей, тем лучше (штрафы меньше).
    """
    d_set = set((dt, did) for (t, dt, did, b) in schedule
                if dt is not None and did is not None and b is not None)
    return len(d_set)

def count_completed_trips(schedule):
    """
    Кол-во рейсов, где dt != None, did != None и b != None.
    """
    return sum(1 for (t, dt, did, b) in schedule
               if dt is not None and did is not None and b is not None)

def count_peak_trips(schedule):
    """
    Кол-во рейсов, начинающихся в пиковый период (7-9 или 17-19).
    """
    return sum(1 for (t, dt, did, b) in schedule
               if dt is not None and did is not None and b is not None
               and is_peak(t['start_min']))

# ФИТНЕС-ФУНКЦИЯ
def fitness(ind):
    """
    Расчёт фитнеса:
      - R: кол-во выполненных рейсов
      - W: уникальные водители
      - penalties: сумма штрафов
      - peak_bonus: бонус за рейсы в пиковое время
    Фитнес = numerator / denominator
      где numerator = ALPHA*(R / R_max + peak_bonus)
          denominator = numerator + BETA*(W / W_max) + penalties*0.01
    """
    schedule = decode_individual(ind)
    R = count_completed_trips(schedule)
    W = count_unique_drivers(schedule)
    extra_buses = count_buses_used(schedule)

    # Штрафы
    p_driver = check_driver_constraints(schedule)
    p_bus    = check_bus_constraints(schedule)
    p_shift  = check_shift_change(schedule)
    p_buses_extra = extra_buses * PENALTY_TOO_MANY_BUSES

    # Пиковые рейсы
    peak_count = count_peak_trips(schedule)
    R_max = len(POSSIBLE_TRIPS)  # всего потенциальных рейсов
    W_max = 30.0 if R_max > 0 else 1.0

    peak_bonus = (peak_count / R_max)*PEAK_BONUS_FACTOR if R_max>0 else 0
    penalties = p_driver + p_bus + p_shift + p_buses_extra

    numerator   = ALPHA*(R / R_max + peak_bonus)
    denominator = ALPHA*(R / R_max + peak_bonus) + BETA*(W / W_max) + penalties*0.01

    if denominator == 0:
        fit = 0
    else:
        fit = numerator / denominator
    return fit

# ОПЕРАЦИИ ГЕНЕТИЧЕСКОГО АЛГОРИТМА
def crossover(p1, p2):
    """
    Одноточечный кроссовер: обмениваемся частью генов между двумя родителями.
    """
    if random.random() > CROSSOVER_PROB:
        return p1[:], p2[:]
    point = random.randint(1, len(p1)-1)
    c1 = p1[:point] + p2[point:]
    c2 = p2[:point] + p1[point:]
    return c1, c2

def mutate(ind):
    """
    Мутация: с вероятностью MUTATION_PROB меняем либо водителя, либо автобус, либо сбрасываем назначение.
    """
    for i in range(len(ind)):
        if random.random() < MUTATION_PROB:
            trip_id, dt, did, b = ind[i]
            if random.random() < 0.3:
                # Иногда сбрасываем назначение или назначаем новое
                if dt is None:
                    new_dt, new_did = random_driver_assignment()
                    new_b = random_bus_assignment()
                    ind[i] = (trip_id, new_dt, new_did, new_b)
                else:
                    ind[i] = (trip_id, None, None, None)
            else:
                # Меняем водителя или автобус
                if dt is not None:
                    # 50%: меняем водителя, 50%: меняем автобус
                    if random.random() < 0.5:
                        new_dt, new_did = random_driver_assignment()
                        ind[i] = (trip_id, new_dt, new_did, b)
                    else:
                        new_b = random_bus_assignment()
                        ind[i] = (trip_id, dt, did, new_b)
                else:
                    new_dt, new_did = random_driver_assignment()
                    new_b = random_bus_assignment()
                    ind[i] = (trip_id, new_dt, new_did, new_b)
    return ind

def selection(pop):
    """
    Турнирная селекция: случайно берём k=5 особей и выбираем лучшую из них.
    pop - список кортежей (fitness_value, individual).
    """
    k = 5
    candidates = random.sample(pop, k)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def genetic_algorithm():
    """
    Запуск основного цикла ГА:
    1) Инициализируем популяцию
    2) Считаем фитнес для каждого индивидуума
    3) Сортируем и берём элитную часть next_population
    4) Делаем кроссовер, мутации до заполнения популяции
    5) Повторяем на протяжении GENERATIONS поколений
    Возвращаем лучший найденный индивидуум и его фитнес.
    """
    population = [init_individual() for _ in range(POP_SIZE)]
    elite_size = 10  # сколько особей сохраняем в поколениях

    for gen in range(GENERATIONS):
        scored = [(fitness(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)
        # элитизм: сохраняем top-10
        next_population = [scored[i][1] for i in range(min(elite_size, POP_SIZE))]

        while len(next_population) < POP_SIZE:
            p1 = selection(scored)
            p2 = selection(scored)
            c1, c2 = crossover(p1, p2)
            c1 = mutate(c1)
            c2 = mutate(c2)
            next_population.append(c1)
            if len(next_population) < POP_SIZE:
                next_population.append(c2)

        population = next_population

        # Периодически выводим прогресс
        if gen % 50 == 0:
            best_fit, best_ind = max(((fitness(i), i) for i in population), key=lambda x: x[0])
            print(f"Поколение {gen}, лучший фитнес: {best_fit:.4f}")

    best_fit, best_ind = max(((fitness(i), i) for i in population), key=lambda x: x[0])
    return best_ind, best_fit

# НАИВНЫЙ АЛГОРИТМ
def greedy_algorithm():
    """
    Простейший наивный алгоритм:
    Всем рейсам одинаково назначаем водителя A1 и автобус 1.
    Штрафы при этом могут быть высокими,
    но даёт точку сравнения с результатами ГА.
    """
    greedy_ind = []
    for trip in POSSIBLE_TRIPS:
        trip_id = trip['id']
        greedy_ind.append((trip_id, 'A', 1, 1))
    return greedy_ind

# ФУНКЦИЯ ДЛЯ ОТОБРАЖЕНИЯ РАСПИСАНИЯ
def display_schedule(ind):
    """
    Выводим в консоль расписание по дням:
    Для каждого дня печатаем рейсы (номер, время, водитель, автобус).
    """
    schedule = decode_individual(ind)
    trips_by_day = {}
    for (tr, dt, did, b) in schedule:
        if dt is not None and did is not None and b is not None:
            day = tr['day']
            if day not in trips_by_day:
                trips_by_day[day] = []
            trips_by_day[day].append((tr, dt, did, b))

    sorted_days = sorted(trips_by_day.keys())
    print("Расписание (выполненные рейсы):")
    for day in sorted_days:
        day_name = DAY_NAMES[day]
        print(f"{day_name}:")
        day_trips = sorted(trips_by_day[day], key=lambda x: x[0]['start_min'])
        for (tr, dt, did, b) in day_trips:
            day_number = day + 1
            print(f"  День {day_number}, Рейс {tr['id']}: "
                  f"{format_time(tr['start_min'])}-{format_time(tr['end_min'])}, "
                  f"Продолжительность: {tr['duration']} мин, Водитель: {dt}{did}, Автобус: {b}")
        print()

# ЗАПУСК ПРОГРАММЫ
if __name__ == "__main__":
    # Запускаем ГА
    best_solution, best_fitness = genetic_algorithm()
    print("Лучший найденный фитнес (Генетический алгоритм):", best_fitness)
    display_schedule(best_solution)

    # Сравниваем с жадным алгоритмом
    greedy_sol = greedy_algorithm()
    greedy_fit = fitness(greedy_sol)
    print("\nСравнение с наивным алгоритмом:")
    print(f"Фитнес наивного алгоритма: {greedy_fit:.4f}")
    if greedy_fit > best_fitness:
        print("Наивный алгоритм показал более высокий фитнес.")
    else:
        print("Генетический алгоритм показал более высокий фитнес.")
