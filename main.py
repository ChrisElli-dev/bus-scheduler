import random

START_TIME = 6 * 60  # 6:00 (360 мин от начала суток)
END_TIME = 27 * 60  # 3:00 следующего дня (1620 мин от начала суток)
TOTAL_TIME = END_TIME - START_TIME  # 1260 минут (21 час)

PEAK_TIMES = [(7 * 60, 9 * 60), (17 * 60, 19 * 60)]
BASE_BUSES = 8

DRIVER_TYPES = ['A', 'A', 'A', 'B', 'B', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'B']

PENALTY_NO_LUNCH_A = 10  # штраф за отсутствие 1ч обеда у A при работе >4ч
PENALTY_OVERTIME_A = 20  # штраф за переработку у A свыше 9ч
PENALTY_B_SHORT_BREAK = 10  # штраф за отсутствие короткого перерыва каждые 2ч для B
PENALTY_B_LONG_BREAK = 15  # штраф за отсутствие долгого перерыва после 2 коротких у B
PENALTY_TOO_MANY_BUSES = 5  # штраф за доп. автобусы
PENALTY_BUS_CONFLICT = 5  # штраф за использование >8 автобусов одновременно
PENALTY_OVERTIME_B = 25  # Новый штраф за превышение 12 часов работы для водителей типа B

# Параметры ГА
POP_SIZE = 60
GENERATIONS = 300
CROSSOVER_PROB = 0.9
MUTATION_PROB = 0.0001

# Весовые коэффициенты фитнеса
ALPHA = 10.0  # важность максимизации числа рейсов
BETA = 0.5  # важность минимизации числа водителей
PEAK_BONUS_FACTOR = 0.1  # бонус за рейсы в пиковые часы

DAYS = 7
DAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# ------------------------------------------
# ГЕНЕРАЦИЯ ПОТЕНЦИАЛЬНЫХ РЕЙСОВ
# ------------------------------------------
def generate_possible_trips():
    trips = []
    trip_id = 1  # Инициализируем trip_id до начала цикла по дням
    for day in range(DAYS):
        start = 0
        while True:
            route_time = random.randint(50, 70)
            if start + route_time <= TOTAL_TIME:
                trips.append({
                    'id': trip_id,
                    'day': day,
                    'start_min': START_TIME + start,
                    'end_min': START_TIME + start + route_time,
                    'duration': route_time
                })
                trip_id += 1  # Увеличиваем trip_id независимо от дня
                start += route_time
            else:
                break
    return trips


POSSIBLE_TRIPS = generate_possible_trips()


# ------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------
def format_time(m):
    h = (m // 60) % 24
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def is_peak(minute_of_day):
    for (sp, ep) in PEAK_TIMES:
        if sp <= minute_of_day < ep:
            return True
    return False


def random_driver_assignment():
    # 20% шанс не назначать водителя
    if random.random() < 0.2:
        return (None, None)
    # Увеличиваем вероятность выбора 'A' до 70%, 'B' до 30%
    dt = random.choices(['A', 'B'], weights=[70, 30], k=1)[0]
    did = random.randint(1, 30)
    return (dt, did)

def random_bus_assignment():
    # 20% шанс не назначать автобус
    if random.random() < 0.2:
        return None
    return random.randint(1, 12)


def decode_individual(ind):
    # Индивидуум представляет собой список назначений для всех рейсов
    schedule = []
    for gene, trip in zip(ind, POSSIBLE_TRIPS):
        dt, did, b = gene
        schedule.append((trip, dt, did, b))
    return schedule


# ------------------------------------------
# ПРОВЕРКА ОГРАНИЧЕНИЙ ДЛЯ ВОДИТЕЛЕЙ
# ------------------------------------------
def check_driver_constraints(schedule):
    drivers_map = {}
    for (t, dt, did, b) in schedule:
        if dt is not None and did is not None and b is not None:
            key = (dt, did)
            if key not in drivers_map:
                drivers_map[key] = []
            drivers_map[key].append(t)

    penalties = 0

    for drv_key, trips in drivers_map.items():
        dt, did = drv_key
        # Сортируем рейсы по дню и времени начала
        trips.sort(key=lambda x: (x['day'], x['start_min']))
        # Группируем рейсы по дням
        trips_by_day = {}
        for tr in trips:
            day = tr['day']
            if day not in trips_by_day:
                trips_by_day[day] = []
            trips_by_day[day].append(tr)

        for day, day_trips in trips_by_day.items():
            # Суммируем фактическую длительность рейсов (t['duration']) за день
            total_work = sum(tr['duration'] for tr in day_trips)
            # Проверка для водителей типа B: не более 720 мин (12 часов) в день
            if dt == 'B' and total_work > 720:
                penalties += PENALTY_OVERTIME_B

            # Считаем промежутки между рейсами
            intervals = []
            for i in range(len(day_trips) - 1):
                gap = day_trips[i + 1]['start_min'] - day_trips[i]['end_min']
                intervals.append(gap)

            if dt == 'A':
                # Правила для A:
                # >4ч (240 мин) без >=60 мин обеда — штраф
                # >9ч (540 мин) — штраф за переработку
                if total_work > PENALTY_OVERTIME_A:
                    penalties += PENALTY_OVERTIME_A
                if total_work > 240:
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
                # Каждые 2ч (120 мин) нужен 15-20 мин перерыв,
                # не более 2 коротких подряд, затем нужен >=60 мин
                work_acc = 0
                short_break_count = 0
                for i in range(len(day_trips) - 1):
                    work_acc += day_trips[i]['duration']
                    gap = intervals[i]
                    if work_acc >= 120:
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
                # Проверим в конце дня
                if work_acc >= 120:
                    penalties += PENALTY_B_SHORT_BREAK

    return penalties

# ------------------------------------------
# ПРОВЕРКА ОГРАНИЧЕНИЙ ПО АВТОБУСАМ
# ------------------------------------------
def check_bus_constraints(schedule):
    usage = [0] * (TOTAL_TIME + 1)
    for (t, dt, did, b) in schedule:
        if b is None or dt is None or did is None:
            continue
        start_i = t['start_min'] - START_TIME
        end_i = t['end_min'] - START_TIME
        for m in range(start_i, end_i):
            if 0 <= m < TOTAL_TIME:
                usage[m] += 1
    penalties = 0
    for x in usage:
        if x > BASE_BUSES:
            penalties += (x - BASE_BUSES) * PENALTY_BUS_CONFLICT
    return penalties


def count_buses_used(schedule):
    b_set = set(b for (t, dt, did, b) in schedule if b is not None and dt is not None and did is not None)
    if not b_set:
        return 0
    max_bus = max(b_set)
    extra = max(0, max_bus - BASE_BUSES)
    return extra


def count_unique_drivers(schedule):
    d_set = set((dt, did) for (t, dt, did, b) in schedule if dt is not None and did is not None and b is not None)
    return len(d_set)


def count_completed_trips(schedule):
    return sum(1 for (t, dt, did, b) in schedule if dt is not None and did is not None and b is not None)


def count_peak_trips(schedule):
    return sum(1 for (t, dt, did, b) in schedule
               if dt is not None and did is not None and b is not None
               and is_peak(t['start_min']))


# ------------------------------------------
# ФИТНЕС-ФУНКЦИЯ
# ------------------------------------------
def fitness(ind):
    schedule = decode_individual(ind)
    R = count_completed_trips(schedule)
    W = count_unique_drivers(schedule)
    extra_buses = count_buses_used(schedule)
    p_driver = check_driver_constraints(schedule)
    p_bus = check_bus_constraints(schedule)
    p_buses_extra = extra_buses * PENALTY_TOO_MANY_BUSES

    peak_count = count_peak_trips(schedule)
    R_max = len(POSSIBLE_TRIPS)  # Общее количество возможных рейсов
    W_max = 30.0 if len(POSSIBLE_TRIPS) > 0 else 1.0
    peak_bonus = (peak_count / R_max) * PEAK_BONUS_FACTOR if R_max > 0 else 0

    penalties = p_driver + p_bus + p_buses_extra

    numerator = ALPHA * (R / R_max + peak_bonus)
    denominator = ALPHA * (R / R_max + peak_bonus) + BETA * (W / W_max) + penalties * 0.01

    if denominator == 0:
        fit = 0
    else:
        fit = numerator / denominator  # Значение в диапазоне [0,1]

    return fit


# ------------------------------------------
# ОПЕРАЦИИ ГА
# ------------------------------------------
def init_individual():
    individual = []
    for trip in POSSIBLE_TRIPS:
        if random.random() < 0.2:
            individual.append((None, None, None))
        else:
            dt, did = random_driver_assignment()
            b = random_bus_assignment()
            if dt is None or b is None:
                individual.append((None, None, None))
            else:
                individual.append((dt, did, b))
    return individual


def crossover(p1, p2):
    if random.random() > CROSSOVER_PROB:
        return p1[:], p2[:]
    point = random.randint(1, len(p1) - 1)
    c1 = p1[:point] + p2[point:]
    c2 = p2[:point] + p1[point:]
    return c1, c2


def mutate(ind):
    for i in range(len(ind)):
        if random.random() < MUTATION_PROB:
            gene = ind[i]
            if random.random() < 0.3:
                if gene[0] is None:
                    dt, did = random_driver_assignment()
                    b = random_bus_assignment()
                    ind[i] = (dt, did, b)
                else:
                    ind[i] = (None, None, None)
            else:
                if gene[0] is not None:
                    if random.random() < 0.5:
                        dt, did = random_driver_assignment()
                        ind[i] = (dt, did, gene[2])
                    else:
                        b = random_bus_assignment()
                        ind[i] = (gene[0], gene[1], b)
                else:
                    dt, did = random_driver_assignment()
                    b = random_bus_assignment()
                    ind[i] = (dt, did, b)
    return ind


def selection(pop):
    k = 4
    candidates = random.sample(pop, k)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def genetic_algorithm():
    population = [init_individual() for _ in range(POP_SIZE)]
    for gen in range(GENERATIONS):
        scored = [(fitness(ind), ind) for ind in population]
        scored.sort(key=lambda x: x[0], reverse=True)
        next_population = [scored[i][1] for i in range(min(5, POP_SIZE))]  # элита

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

        if gen % 50 == 0:
            best_fit, best_ind = max(((fitness(i), i) for i in population), key=lambda x: x[0])
            print(f"Поколение {gen}, лучший фитнес: {best_fit:.4f}")

    best_fit, best_ind = max(((fitness(i), i) for i in population), key=lambda x: x[0])
    return best_ind, best_fit

# ------------------------------------------
# ФУНКЦИЯ ДЛЯ ОТОБРАЖЕНИЯ РАСПИСАНИЯ
# ------------------------------------------
def display_schedule(best_ind):
    schedule = decode_individual(best_ind)
    # Группируем рейсы по дням
    trips_by_day = {}
    for (tr, dt, did, b) in schedule:
        if dt is not None and did is not None and b is not None:
            day = tr['day']
            if day not in trips_by_day:
                trips_by_day[day] = []
            trips_by_day[day].append((tr, dt, did, b))

    # Сортируем дни по порядку
    sorted_days = sorted(trips_by_day.keys())

    print("Расписание (выполненные рейсы):")
    for day in sorted_days:
        day_name = DAY_NAMES[day]
        print(f"{day_name}:")
        # Сортируем рейсы по времени начала
        day_trips = sorted(trips_by_day[day], key=lambda x: x[0]['start_min'])
        for (tr, dt, did, b) in day_trips:
            day_number = day + 1
            print(f"День {day_number}, Рейс {tr['id']}: {format_time(tr['start_min'])}-{format_time(tr['end_min'])}, "
                  f"Продолжительность: {tr['duration']} мин, Водитель: {dt}{did}, Автобус: {b}")
        print()  # Пустая строка между днями

if __name__ == "__main__":
    best_solution, best_fitness = genetic_algorithm()
    print("Лучший найденный фитнес:", best_fitness)
    display_schedule(best_solution)
