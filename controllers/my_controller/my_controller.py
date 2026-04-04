from controller import Robot, Camera, Motor, GPS, InertialUnit
import random
import math

TIME_STEP = 64
MAX_SPEED = 6.28

robot = Robot()

# =========================
# Motors
# =========================
left_motor = robot.getDevice('left wheel motor')
right_motor = robot.getDevice('right wheel motor')

left_motor.setPosition(float('inf'))
right_motor.setPosition(float('inf'))
left_motor.setVelocity(0.0)
right_motor.setVelocity(0.0)

# =========================
# Camera
# =========================
camera = robot.getDevice('camera')
camera.enable(TIME_STEP)

# =========================
# GPS + IMU
# =========================
gps = robot.getDevice('gps')
if gps is not None:
    gps.enable(TIME_STEP)

imu = robot.getDevice('inertial unit')
if imu is not None:
    imu.enable(TIME_STEP)

# =========================
# Proximity sensors
# =========================
ps_names = ['ps0', 'ps1', 'ps2', 'ps3', 'ps4', 'ps5', 'ps6', 'ps7']
ps = []
for name in ps_names:
    s = robot.getDevice(name)
    s.enable(TIME_STEP)
    ps.append(s)

# =========================
# Ground sensors
# =========================
gs_names = ['gs0', 'gs1', 'gs2']
gs = []
for name in gs_names:
    s = robot.getDevice(name)
    if s:
        s.enable(TIME_STEP)
        gs.append(s)

# =========================
# Internal needs
# =========================
MAX_HUNGER = 1000
MAX_THIRST = 1000
MAX_TIREDNESS = 1000

hunger = 0
thirst = 0
tiredness = 0

HUNGER_THRESHOLD = 600
THIRST_THRESHOLD = 700
TIRED_THRESHOLD = 750

RESOURCE_PATCH_THRESHOLD = 600

# =========================
# Sleep
# =========================
SLEEP_X, SLEEP_Y = 0.328, 0.335
SLEEP_NEAR_DISTANCE = 0.08
SLEEP_DURATION_STEPS = int((30 * 1000) / TIME_STEP)
sleep_timer = 0

# =========================
# Existential
# =========================
existential_mode = False
existential_timer = 0
EXISTENTIAL_DURATION = 56
idle_existential_done = False

# =========================
# Mutation Mode
# =========================
mutation_mode = False
mutation_type = None
mutation_timer = 0
MUTATION_DURATION = int((4 * 1000) / TIME_STEP)
MUTATION_CHANCE = 0.01
mutation_cycle = ["HYPER", "LAZY", "CONFUSED", "ERRATIC"]
mutation_index = 0

# =========================
# State
# =========================
state = "EXPLORE"
goal = None

wander_timer = 0
wander_dir = 1

search_timer = 0
search_mode = "FORWARD"

rest_timer = 0
recover_timer = 0

status_print_timer = 0
consume_print_timer = 0
blood_print_timer = 0

# =========================
# Memory
# =========================
last_seen_food = False
last_seen_water = False

food_memory_pos = None
water_memory_pos = None

last_seen_food_timer = 0
last_seen_water_timer = 0
food_memory_side = "CENTER"
water_memory_side = "CENTER"
MEMORY_DURATION = 80

# =========================
# Rest timing
# =========================
REST_AFTER_EAT = 45
REST_AFTER_DRINK = 45
REST_AFTER_SLEEP = 45

# =========================
# Stuck / recovery detection
# =========================
blocked_counter = 0
avoid_counter = 0

# =========================
# GPS heading memory
# =========================
prev_gps_pos = None

# =========================
# RED / PANIC CONTROL
# =========================
panic_red_timer = 0
PANIC_RED_DURATION = 16
RED_ENTER_THRESHOLD = 18
RED_EXIT_THRESHOLD = 8
last_red_side = "CENTER"

# =========================
# Helper functions
# =========================
def clamp_speed(v):
    return max(-MAX_SPEED, min(MAX_SPEED, v))

def set_speed(l, r):
    global mutation_mode, mutation_type

    if mutation_mode:
        if mutation_type == "HYPER":
            l *= 1.3
            r *= 1.3
        elif mutation_type == "LAZY":
            l *= 0.6
            r *= 0.6
        elif mutation_type == "CONFUSED":
            l += random.uniform(-0.6, 0.6)
            r += random.uniform(-0.6, 0.6)
        elif mutation_type == "ERRATIC":
            if random.random() < 0.2:
                l, r = r, l

    left_motor.setVelocity(clamp_speed(l))
    right_motor.setVelocity(clamp_speed(r))

def read_proximity():
    return [p.getValue() for p in ps]

def read_ground():
    return [g.getValue() for g in gs] if gs else [1000, 1000, 1000]

def obstacle_detected(values):
    fl = values[7] + values[0]
    fr = values[1] + values[2]
    fc = values[0] + values[7] + values[1]

    front_left = max(values[7], values[0])
    front_right = max(values[1], values[2])

    blocked = (
        fc > 240 or
        fl > 180 or
        fr > 180 or
        front_left > 120 or
        front_right > 120
    )

    return blocked, fl, fr, fc

def on_patch(g):
    return sum(g) / len(g) < RESOURCE_PATCH_THRESHOLD

def hunger_percent():
    return int(hunger / MAX_HUNGER * 100)

def fullness_percent():
    return 100 - hunger_percent()

def thirst_percent():
    return int(thirst / MAX_THIRST * 100)

def tired_percent():
    return int(tiredness / MAX_TIREDNESS * 100)

def energy_percent():
    return 100 - tired_percent()

def choose_search_mode():
    return random.choice([
        "FORWARD",
        "FORWARD_LEFT",
        "FORWARD_RIGHT",
        "SCAN_LEFT",
        "SCAN_RIGHT"
    ])

def get_floor_color_scores():
    width = camera.getWidth()
    height = camera.getHeight()
    image = camera.getImage()

    green_left = 0
    green_right = 0
    blue_left = 0
    blue_right = 0

    for x in range(width // 6, 5 * width // 6, 2):
        for y in range(height // 2, height, 2):
            r = camera.imageGetRed(image, width, x, y)
            g = camera.imageGetGreen(image, width, x, y)
            b = camera.imageGetBlue(image, width, x, y)

            is_green = (g > 80 and g > r + 25 and g > b + 25)
            is_blue = (b > 80 and b > r + 20 and b > g + 10)

            if is_green:
                if x < width // 2:
                    green_left += 1
                else:
                    green_right += 1

            if is_blue:
                if x < width // 2:
                    blue_left += 1
                else:
                    blue_right += 1

    green_total = green_left + green_right
    blue_total = blue_left + blue_right
    return green_total, green_left, green_right, blue_total, blue_left, blue_right

def get_yellow_zone_info():
    width = camera.getWidth()
    height = camera.getHeight()
    image = camera.getImage()

    yellow_total = 0

    for x in range(width // 8, 7 * width // 8, 2):
        for y in range(height // 3, 5 * height // 6, 2):
            r = camera.imageGetRed(image, width, x, y)
            g = camera.imageGetGreen(image, width, x, y)
            b = camera.imageGetBlue(image, width, x, y)

            is_yellow = (
                r > 100 and
                g > 100 and
                abs(r - g) < 60 and
                b < 90
            )

            if is_yellow:
                yellow_total += 1

    return yellow_total

def get_red_zone_info():
    width = camera.getWidth()
    height = camera.getHeight()
    image = camera.getImage()

    red_left = 0
    red_right = 0
    red_total = 0

    for x in range(width // 8, 7 * width // 8, 2):
        for y in range(height // 2, height - 2, 2):
            r = camera.imageGetRed(image, width, x, y)
            g = camera.imageGetGreen(image, width, x, y)
            b = camera.imageGetBlue(image, width, x, y)

            is_red = (
                r > 95 and
                r > g + 35 and
                r > b + 35 and
                g < 120 and
                b < 120
            )

            if is_red:
                red_total += 1
                if x < width // 2:
                    red_left += 1
                else:
                    red_right += 1

    return red_total, red_left, red_right

def yellow_visible(y):
    return y > 15

def update_memory_side(left_score, right_score):
    if left_score > right_score + 4:
        return "LEFT"
    elif right_score > left_score + 4:
        return "RIGHT"
    return "CENTER"

def drive_using_memory(side, base_speed=3.2):
    if side == "LEFT":
        set_speed(1.4, base_speed)
    elif side == "RIGHT":
        set_speed(base_speed, 1.4)
    else:
        set_speed(base_speed, base_speed)

def do_search_motion():
    global search_timer, search_mode

    search_timer -= 1
    if search_timer <= 0:
        search_mode = choose_search_mode()
        search_timer = random.randint(20, 40)

    if search_mode == "FORWARD":
        set_speed(3.0, 3.0)
    elif search_mode == "FORWARD_LEFT":
        set_speed(2.5, 3.2)
    elif search_mode == "FORWARD_RIGHT":
        set_speed(3.2, 2.5)
    elif search_mode == "SCAN_LEFT":
        set_speed(-0.6, 1.6)
    elif search_mode == "SCAN_RIGHT":
        set_speed(1.6, -0.6)

def get_position():
    return gps.getValues() if gps else None

def angle_wrap(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a

def get_heading_from_imu():
    if imu is None:
        return None
    return imu.getRollPitchYaw()[2]

def get_heading_from_gps():
    global prev_gps_pos
    pos = get_position()
    if pos is None:
        return None

    if prev_gps_pos is None:
        prev_gps_pos = [pos[0], pos[1], pos[2]]
        return None

    dx = pos[0] - prev_gps_pos[0]
    dy = pos[1] - prev_gps_pos[1]
    prev_gps_pos = [pos[0], pos[1], pos[2]]

    if abs(dx) < 1e-5 and abs(dy) < 1e-5:
        return None

    return math.atan2(dy, dx)

def navigate_to_point(tx, ty, stop=0.04):
    pos = get_position()
    if pos is None:
        return False

    dx, dy = tx - pos[0], ty - pos[1]
    dist = math.sqrt(dx * dx + dy * dy)

    if dist < stop:
        set_speed(0, 0)
        return True

    target_angle = math.atan2(dy, dx)

    heading = get_heading_from_imu()
    if heading is None:
        heading = get_heading_from_gps()

    if heading is None:
        set_speed(2.0, 2.6)
        return False

    error = angle_wrap(target_angle - heading)

    base = 3.0 if dist > 0.10 else 2.0
    turn = 2.0 * error

    set_speed(base - turn, base + turn)
    return False

def navigate_to_memory(target_pos):
    if target_pos is None:
        return False
    return navigate_to_point(target_pos[0], target_pos[1], stop=0.04)

def navigate_to_sleep(tx, ty):
    return navigate_to_point(tx, ty, stop=SLEEP_NEAR_DISTANCE)

def panic_escape_motion(red_left, red_right, blocked, fl, fr):
    global last_red_side

    if red_left > red_right + 4:
        last_red_side = "LEFT"
    elif red_right > red_left + 4:
        last_red_side = "RIGHT"

    if blocked:
        if last_red_side == "LEFT":
            set_speed(-3.8, -1.2)
        elif last_red_side == "RIGHT":
            set_speed(-1.2, -3.8)
        else:
            if fl >= fr:
                set_speed(-3.6, -1.4)
            else:
                set_speed(-1.4, -3.6)
        return

    if last_red_side == "LEFT":
        set_speed(4.8, 2.0)
    elif last_red_side == "RIGHT":
        set_speed(2.0, 4.8)
    else:
        set_speed(-3.0, -4.6)

# =========================
# MAIN LOOP
# =========================
while robot.step(TIME_STEP) != -1:
    hunger += 1
    thirst += 1
    tiredness += 1

    hunger = min(hunger, MAX_HUNGER)
    thirst = min(thirst, MAX_THIRST)
    tiredness = min(tiredness, MAX_TIREDNESS)

    if last_seen_food_timer > 0:
        last_seen_food_timer -= 1
    else:
        last_seen_food = False
        food_memory_side = "CENTER"

    if last_seen_water_timer > 0:
        last_seen_water_timer -= 1
    else:
        last_seen_water = False
        water_memory_side = "CENTER"

    prox = read_proximity()
    ground = read_ground()
    blocked, fl, fr, fc = obstacle_detected(prox)

    green_total, green_left, green_right, blue_total, blue_left, blue_right = get_floor_color_scores()
    yellow_total = get_yellow_zone_info()
    red_total, red_left, red_right = get_red_zone_info()

    green_visible = (green_total > 25) and (green_total > blue_total * 1.4)
    blue_visible = (blue_total > 25) and (blue_total > green_total * 1.4)
    yellow_seen = yellow_visible(yellow_total)

    if panic_red_timer > 0:
        red_seen = red_total > RED_EXIT_THRESHOLD
    else:
        red_seen = red_total > RED_ENTER_THRESHOLD

    yellow_patch = on_patch(ground) and yellow_seen

    if green_visible:
        last_seen_food = True
        last_seen_food_timer = MEMORY_DURATION
        food_memory_side = update_memory_side(green_left, green_right)

    if blue_visible:
        last_seen_water = True
        last_seen_water_timer = MEMORY_DURATION
        water_memory_side = update_memory_side(blue_left, blue_right)

    if blocked:
        blocked_counter += 1
    else:
        blocked_counter = max(0, blocked_counter - 1)

    if goal is None:
        if tiredness >= TIRED_THRESHOLD:
            goal = "SLEEP"
            search_timer = 0
        elif hunger >= HUNGER_THRESHOLD:
            goal = "FOOD"
            search_timer = 0
        elif thirst >= THIRST_THRESHOLD:
            goal = "WATER"
            search_timer = 0

    if goal is not None:
        idle_existential_done = False

    if goal == "FOOD" and hunger <= 0:
        goal = None
        last_seen_food = False
        last_seen_food_timer = 0
        food_memory_side = "CENTER"

    if goal == "WATER" and thirst <= 0:
        goal = None
        last_seen_water = False
        last_seen_water_timer = 0
        water_memory_side = "CENTER"

    if goal == "SLEEP" and tiredness <= 0:
        goal = None

    if red_seen:
        panic_red_timer = PANIC_RED_DURATION
    elif panic_red_timer > 0:
        panic_red_timer -= 1

    if recover_timer > 0 or blocked_counter > 10 or avoid_counter > 16:
        state = "RECOVER"
        if recover_timer <= 0:
            recover_timer = 24

    elif panic_red_timer > 0:
        state = "ESCAPE_RED"

    elif rest_timer > 0:
        state = "REST"

    elif blocked and state not in ["EAT", "DRINK", "SLEEP", "REST", "EXISTENTIAL"]:
        state = "AVOID"

    elif existential_mode and goal is None:
        state = "EXISTENTIAL"

    elif goal == "FOOD":
        state = "SEARCH_FOOD" if (not on_patch(ground) or not (last_seen_food or green_visible)) else "EAT"

    elif goal == "WATER":
        state = "SEARCH_WATER" if (not on_patch(ground) or not (last_seen_water or blue_visible)) else "DRINK"

    elif goal == "SLEEP":
        if yellow_patch:
            if state != "SLEEP":
                sleep_timer = 0
            state = "SLEEP"
        else:
            pos = get_position()
            if pos:
                dist = math.hypot(SLEEP_X - pos[0], SLEEP_Y - pos[1])
            else:
                dist = 999

            if dist <= SLEEP_NEAR_DISTANCE:
                if state != "SLEEP":
                    sleep_timer = 0
                state = "SLEEP"
            else:
                state = "GO_SLEEP"

    else:
        if not idle_existential_done:
            existential_mode = True
            existential_timer = 0
            idle_existential_done = True
            state = "EXISTENTIAL"
        else:
            if random.random() < 0.3:
                state = "WANDER"
            else:
                state = "EXPLORE"

    if state == "AVOID":
        avoid_counter += 1
    else:
        avoid_counter = max(0, avoid_counter - 1)

    if not mutation_mode and state in ["EXPLORE", "WANDER"]:
        if random.random() < MUTATION_CHANCE:
            mutation_mode = True
            mutation_timer = 0
            mutation_type = mutation_cycle[mutation_index]
            mutation_index = (mutation_index + 1) % len(mutation_cycle)
            print("MUTATION ACTIVATED:", mutation_type)

    if mutation_mode:
        mutation_timer += 1
        if mutation_timer >= MUTATION_DURATION:
            print("Mutation ended")
            mutation_mode = False
            mutation_type = None
            mutation_timer = 0

    status_print_timer -= 1
    if status_print_timer <= 0:
        print(
            "STATE:", state,
            "| GOAL:", goal,
            "| Hunger:", hunger_percent(),
            "| Thirst:", thirst_percent(),
            "| Energy:", energy_percent(),
            "| Existential Crisis:", existential_mode,
            "| Mutation:", mutation_type,
        )
        status_print_timer = 15

    # =========================
    # BEHAVIOURS
    # =========================
    if state == "ESCAPE_RED":
        if blood_print_timer <= 0:
            print("BLOOD!!")
            blood_print_timer = 8
        else:
            blood_print_timer -= 1

        panic_escape_motion(red_left, red_right, blocked, fl, fr)

    elif state == "RECOVER":
        recover_timer -= 1

        if recover_timer > 14:
            set_speed(-3.6, -3.6)
        elif recover_timer > 6:
            if fl >= fr:
                set_speed(3.2, -3.2)
            else:
                set_speed(-3.2, 3.2)
        else:
            set_speed(2.8, 2.8)

        if recover_timer <= 0:
            blocked_counter = 0
            avoid_counter = 0
            panic_red_timer = 0

    elif state == "REST":
        set_speed(0, 0)
        rest_timer -= 1

    elif state == "EXISTENTIAL":
        if existential_timer < 24:
            if existential_timer % 16 < 8:
                set_speed(1.2, 4.2)
            else:
                set_speed(4.2, 1.2)
        else:
            set_speed(4.8, -4.8)

        existential_timer += 1

        if existential_timer >= EXISTENTIAL_DURATION:
            existential_mode = False
            existential_timer = 0
            state = "EXPLORE"

    elif state == "AVOID":
        diff = fl - fr

        if abs(diff) < 20:
            set_speed(-2.2, -2.2)
        elif diff > 0:
            set_speed(-1.6, -2.8)
        else:
            set_speed(-2.8, -1.6)

    elif state == "WANDER":
        wander_timer -= 1
        if wander_timer <= 0:
            wander_timer = random.randint(20, 45)
            wander_dir = random.choice([-1, 1])

        if wander_timer > 28:
            set_speed(3.0, 3.0)
        else:
            if wander_dir == -1:
                set_speed(2.2, 3.0)
            else:
                set_speed(3.0, 2.2)

    elif state == "EXPLORE":
        wander_timer -= 1
        if wander_timer <= 0:
            wander_timer = random.randint(35, 70)
            wander_dir = random.choice([-1, 1])

        if wander_dir == -1:
            set_speed(3.2, 3.8)
        else:
            set_speed(3.8, 3.2)

    elif state == "SEARCH_FOOD":
        if food_memory_pos is not None and not green_visible and not last_seen_food:
            navigate_to_memory(food_memory_pos)
        elif green_visible:
            if green_left > green_right + 6:
                set_speed(2.0, 3.0)
            elif green_right > green_left + 6:
                set_speed(3.0, 2.0)
            else:
                set_speed(3.1, 3.1)
        elif last_seen_food:
            drive_using_memory(food_memory_side, 3.2)
        else:
            do_search_motion()

    elif state == "EAT":
        set_speed(0, 0)
        hunger -= 15
        hunger = max(0, hunger)

        consume_print_timer -= 1
        if consume_print_timer <= 0:
            print("EATING... Fullness =", str(fullness_percent()) + "%")
            consume_print_timer = 5

        if hunger == 0:
            print("FULL. Fullness = 100%")
            pos = get_position()
            if pos is not None:
                food_memory_pos = (pos[0], pos[1])

            goal = None
            last_seen_food = False
            last_seen_food_timer = 0
            food_memory_side = "CENTER"
            rest_timer = REST_AFTER_EAT
            state = "REST"

    elif state == "SEARCH_WATER":
        if water_memory_pos is not None and not blue_visible and not last_seen_water:
            navigate_to_memory(water_memory_pos)
        elif blue_visible:
            if blue_left > blue_right + 6:
                set_speed(2.0, 3.0)
            elif blue_right > blue_left + 6:
                set_speed(3.0, 2.0)
            else:
                set_speed(3.1, 3.1)
        elif last_seen_water:
            drive_using_memory(water_memory_side, 3.2)
        else:
            do_search_motion()

    elif state == "DRINK":
        set_speed(0, 0)
        thirst -= 15
        thirst = max(0, thirst)

        consume_print_timer -= 1
        if consume_print_timer <= 0:
            print("DRINKING... Thirst =", str(thirst_percent()) + "%")
            consume_print_timer = 5

        if thirst == 0:
            print("DONE DRINKING. Thirst = 0%")
            pos = get_position()
            if pos is not None:
                water_memory_pos = (pos[0], pos[1])

            goal = None
            last_seen_water = False
            last_seen_water_timer = 0
            water_memory_side = "CENTER"
            rest_timer = REST_AFTER_DRINK
            state = "REST"

    elif state == "GO_SLEEP":
        arrived = navigate_to_sleep(SLEEP_X, SLEEP_Y)
        if arrived:
            set_speed(0, 0)
            sleep_timer = 0
            state = "SLEEP"

    elif state == "SLEEP":
        set_speed(0, 0)
        sleep_timer += 1

        consume_print_timer -= 1
        if consume_print_timer <= 0:
            elapsed = int((sleep_timer * TIME_STEP) / 1000)
            print(f"SLEEPING... {elapsed}/30s")
            consume_print_timer = 5

        if sleep_timer >= SLEEP_DURATION_STEPS:
            print("RESTED. Sleep complete.")
            tiredness = 0
            goal = None
            state = "REST"
            rest_timer = REST_AFTER_SLEEP
            sleep_timer = 0
            consume_print_timer = 0

    else:
        set_speed(0, 0)