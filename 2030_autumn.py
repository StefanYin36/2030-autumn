import os
import csv
import math
import traceback
import powerfactory

# ============================================================
# test_pf.py
# PowerFactory 内部运行版
# 功能：
# 1) 删除旧 Grid / Grid(1)，重新导入 CSV
# 2) 导入 buses / lines / loads / generators / external grids
# 3) 从 pf_buses.csv 导入经纬度到 ElmTerm，用于 Geografisch / OpenStreetMap 显示
# 4) 运行 AC Load Flow
# 5) 将完整计算结果导出为 CSV
#
# 用法：
# 1) 先用 D:\PowerFactory.exe - Verknüpfung.lnk 打开 PowerFactory
# 2) 在 PowerFactory 的 DIgSILENT-Bibliothek\Skripte 中运行 loader
# 3) loader 执行本文件：D:\BA Projekt\test_pf.py
# ============================================================

# ==============================
# 1. 用户设置
# ==============================

PROJECT_NAME = "Analysis of Renewable Energy Penetration"

# 这个文件夹里应包含：
# pf_buses.csv, pf_lines.csv, pf_loads.csv, pf_generators.csv, pf_external_grid.csv
# 如果要导入 HVDC 等效注入，还应包含：
# pf_hvdc_loads.csv, pf_hvdc_generators.csv, pf_hvdc_summary.csv
PF_IMPORT_DIR = r"D:\py_import\2030 1.0 py\autumn"

GRID_NAME = "PyPSA_Imported_Grid_pf098_2030_autumn"
STUDY_CASE_NAME = "Berechnungsfall_2030_autumn"

IMPORT_BUSES = True
IMPORT_LINES = True
IMPORT_LOADS = True
IMPORT_GENERATORS = True
IMPORT_EXTERNAL_GRID = True

# HVDC 等效建模：
# 不创建真实 DC 支路/换流站，而是按 CSV 中的稳态功率计划导入为：
#   - 注入端：ElmGenstat
#   - 受端：ElmLod
# 如果 pf_loads.csv / pf_generators.csv 已经包含这些 HVDC 行，再读单独的
# pf_hvdc_*.csv 只会更新同名对象，不会重复创建。
IMPORT_HVDC_EQUIVALENTS = True
HVDC_LOADS_FILE = "pf_hvdc_loads.csv"
HVDC_GENERATORS_FILE = "pf_hvdc_generators.csv"
HVDC_SUMMARY_FILE = "pf_hvdc_summary.csv"

# HVDC 无功模式：
#   CAPABILITY: q_mvar 作为初值 0，按 HVDC_Q_SUPPORT_RATIO 设置 q_min/q_max 可调能力。
#   FIXED:      q_mvar 作为固定无功设定值。
HVDC_Q_SUPPORT_MODE = "CAPABILITY"
HVDC_Q_SUPPORT_RATIO = 0.30
# "PV" 表示让聚合 HVDC qcap 设备参与电压/无功调节。
# 如果外层迭代不收敛，可以临时改回 "PQ" 做对比。
HVDC_Q_CAPABILITY_CONTROL_MODE = "STATION"

# 每个非 Slack bus 创建一个 ElmStactrl，让同 bus 上所有具备 Q 能力的机组共同调压。
ENABLE_STATION_CONTROLLER_BY_BUS = True
STATION_CONTROLLER_U_SETPOINT = 1.0
STATION_CONTROLLER_MIN_PARTICIPANTS = 2
STATION_CONTROLLER_NAME_PREFIX = "stactrl_"

# FIXED 模式下，当 HVDC generator CSV 没有 q_min_mvar / q_max_mvar 时，
# 把 Q 限制锁在 q_mvar。CAPABILITY 模式下此开关不生效。
LOCK_HVDC_GENERATOR_Q_TO_CSV = False

# HVDC 有功吸收端当前用 ElmLod 表示。ElmLod 不能自动调 Q，所以在
# CAPABILITY 模式下为这些 bus 额外创建 0 MW ElmGenstat，只用于无功调节。
CREATE_HVDC_Q_SUPPORT_DEVICE_AT_LOAD_END = True

# 是否从 pf_buses.csv 写入 bus 地理坐标，用于 PowerFactory Geografisch / OpenStreetMap 显示
# pf_buses.csv 中应包含 longitude / latitude，或者 x / y。
# PyPSA 通常 x=longitude, y=latitude。
IMPORT_BUS_GEO_COORDINATES = True

# 如果旧 Grid 或 Grid(1) 已存在，建议 True，避免残留对象干扰。
DELETE_EXISTING_GRID = True

# 如果 pf_buses.csv 里仍有 carrier 列，本脚本只导入 AC，自动忽略 H2 / battery。
ONLY_IMPORT_AC_BUSES = True
AC_CARRIER_NAME = "AC"

# 跳过没有 AC 线路连接的孤立 bus。
# 如果你希望保留 DK1_0 独立小岛，并且 pf_external_grid.csv 里有 slack_DK1_0，请保持 False。
SKIP_BUSES_WITHOUT_AC_LINES = False

# 负荷和发电机命名加前缀，避免与母线重名。
LOAD_NAME_PREFIX = "load_"
GEN_NAME_PREFIX = "gen_"

RUN_DC_LOAD_FLOW = False
RUN_AC_LOAD_FLOW = True

# 如果 pf_external_grid.csv 缺失或为空，至少在这个 bus 上创建一个 External Grid。
DEFAULT_SLACK_BUS = "AT0_0"
REQUIRED_SLACK_BUSES = ["AT0_0", "DK1_0"]

# 对等值系统而言，slack 主要是参考和平衡对象。开启后会尝试把 ElmXnet 的
# Q 上下限放宽，避免外部电网因默认无功限值过早碰到 Q 限。
RELAX_EXTERNAL_GRID_Q_LIMITS = True
EXTERNAL_GRID_Q_LIMIT_MVAR = 1000000.0

# 结果导出设置
EXPORT_RESULTS_TO_CSV = True
RESULT_EXPORT_DIR = r"D:\BA Projekt\pf_results_2030_autumn_station_control"

# Verteilter Slack 诊断：不修改 GUI / Study Case 中已有的分布式 Slack 设置，
# 只读取 ComLdf 相关属性，并比较发电机计划出力 pgini 与潮流结果。
ENABLE_DISTRIBUTED_SLACK_DIAGNOSTICS = True
DISTRIBUTED_SLACK_DELTA_P_TOLERANCE_MW = 0.01

# 线路容量设置
# True: 使用 pf_lines.csv 中的 s_max_pu 折减容量，例如 rated_mva * 0.8，用于安全裕度分析。
# False: 使用 rated_mva 原始容量。
USE_PYPSA_S_MAX_PU_FOR_LINE_RATING = True

# 发电机无功调节设置：读取 pf_generators.csv 中的 q_min_mvar / q_max_mvar / pf_control_mode
# 0.98 功率因数对应 q_ratio = tan(acos(0.98)) ≈ 0.203058661
ENABLE_GENERATOR_Q_CAPABILITY = True
DEFAULT_GENERATOR_COS_PHI = 0.98
DEFAULT_Q_RATIO = 0.203058661

# 是否把 CSV 中 pf_control_mode = PV 的发电机设置为电压控制。
# 注意：PowerFactory 不同版本 ElmGenstat 属性名不同，脚本会尝试多个属性名。
ENABLE_GENERATOR_PV_CONTROL = True

# 如果 PV 控制没有生效，可临时开启这个选项，强制让部分发电机吸收无功进行敏感性测试。
# 正常建议保持 False。
FORCE_GENERATOR_INITIAL_Q_BY_COSPHI = False
FORCE_GENERATOR_Q_SIGN = -1.0  # -1 表示吸收无功，+1 表示注入无功


# ==============================
# 2. 日志函数
# ==============================

def log(app, msg=""):
    text = str(msg)
    print(text)
    try:
        app.PrintPlain(text)
    except Exception:
        pass


def log_section(app, title):
    log(app, "")
    log(app, "=" * 70)
    log(app, title)
    log(app, "=" * 70)


# ==============================
# 3. 工具函数
# ==============================

def read_csv_dict(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"找不到 CSV 文件: {path}")

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    return rows


def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = str(value).strip()
        if value == "":
            return default
        return float(value)
    except Exception:
        return default


def get_lon_lat_from_bus_row(row):
    """
    从 pf_buses.csv 读取经纬度。

    支持列名：
      longitude / latitude
      lon / lat
      x / y

    PyPSA 通常：
      x = longitude 经度
      y = latitude  纬度
    """
    lon = None
    lat = None

    for key in ["longitude", "lon", "x"]:
        if key in row:
            value = str(row.get(key, "")).strip()
            if value != "":
                lon = to_float(value, None)
                break

    for key in ["latitude", "lat", "y"]:
        if key in row:
            value = str(row.get(key, "")).strip()
            if value != "":
                lat = to_float(value, None)
                break

    return lon, lat


def try_set_pf_attribute(obj, attr_names, value):
    """
    尝试用 setattr 和 SetAttribute 两种方式写 PowerFactory 属性。
    返回成功的属性名；失败返回空字符串。
    """
    for attr in attr_names:
        try:
            setattr(obj, attr, value)
            return attr
        except Exception:
            pass

        try:
            obj.SetAttribute(attr, value)
            return attr
        except Exception:
            pass

    return ""


def set_terminal_geo_coordinates(app, term, row):
    """
    给 ElmTerm 写入地理坐标。

    PowerFactory 不同版本中属性名可能不同，所以尝试多个候选名。

    逻辑：
      longitude / x -> Ostwert / Easting / GPS longitude
      latitude  / y -> Nordwert / Northing / GPS latitude

    注意：
      德语界面显示的 Nordwert / Ostwert 不一定就是 Python API 属性名，
      所以这里会尝试 GPSlon/GPSlat、longitude/latitude、x/y、east/north 等多个字段。
    """
    if not IMPORT_BUS_GEO_COORDINATES:
        return False

    lon, lat = get_lon_lat_from_bus_row(row)

    if lon is None or lat is None:
        return False

    # 欧洲范围经纬度简单检查
    if not (-30.0 <= lon <= 60.0 and 30.0 <= lat <= 75.0):
        log(app, "警告：bus 坐标看起来不正常: " + term.loc_name + " lon=" + str(lon) + " lat=" + str(lat))

    # 经度 longitude / Ostwert / Easting
    lon_attr = try_set_pf_attribute(
        term,
        [
            "GPSlon",
            "gpslon",
            "GPSLon",
            "GpsLon",
            "GPSlondeg",
            "gpslondeg",
            "longitude",
            "Longitude",
            "lon",
            "Lon",
            "x",
            "X",
        ],
        lon,
    )

    # 纬度 latitude / Nordwert / Northing
    lat_attr = try_set_pf_attribute(
        term,
        [
            "GPSlat",
            "gpslat",
            "GPSLat",
            "GpsLat",
            "GPSlatdeg",
            "gpslatdeg",
            "latitude",
            "Latitude",
            "lat",
            "Lat",
            "y",
            "Y",
        ],
        lat,
    )

    # 如果 GPS / lon / lat 没写入成功，再尝试德语/英语坐标字段名
    if not lon_attr:
        lon_attr = try_set_pf_attribute(
            term,
            [
                "Ostwert",
                "ostwert",
                "easting",
                "Easting",
                "east",
                "East",
                "coord_east",
                "coordEast",
                "xgeo",
                "Xgeo",
            ],
            lon,
        )

    if not lat_attr:
        lat_attr = try_set_pf_attribute(
            term,
            [
                "Nordwert",
                "nordwert",
                "northing",
                "Northing",
                "north",
                "North",
                "coord_north",
                "coordNorth",
                "ygeo",
                "Ygeo",
            ],
            lat,
        )

    # 把经纬度也写入 desc，方便你之后在对象属性里确认 CSV 坐标是否读到了
    try:
        old_desc = str(term.desc)
        if old_desc == "None":
            old_desc = ""
        if "longitude=" not in old_desc and "latitude=" not in old_desc:
            term.desc = old_desc + "; longitude=" + str(lon) + "; latitude=" + str(lat)
    except Exception:
        try:
            term.desc = "longitude=" + str(lon) + "; latitude=" + str(lat)
        except Exception:
            pass

    if lon_attr or lat_attr:
        return True

    return False


def safe_name(name):
    name = str(name).strip()
    name = name.replace(" ", "_")
    name = name.replace("/", "_")
    name = name.replace("\\", "_")
    name = name.replace(":", "_")
    name = name.replace(";", "_")
    name = name.replace(",", "_")
    name = name.replace("(", "_")
    name = name.replace(")", "_")
    name = name.replace("[", "_")
    name = name.replace("]", "_")
    return name


def set_in_service(obj):
    try:
        obj.outserv = 0
    except Exception:
        pass


def set_out_of_service(obj):
    try:
        obj.outserv = 1
    except Exception:
        pass


def is_in_service(obj):
    try:
        return int(obj.outserv) == 0
    except Exception:
        return True


def get_project_folder_or_none(app, folder_name):
    try:
        return app.GetProjectFolder(folder_name)
    except Exception:
        return None


def delete_object_if_possible(app, obj):
    try:
        obj_name = obj.loc_name
    except Exception:
        obj_name = str(obj)

    try:
        try:
            obj.Deactivate()
            log(app, "已 Deactivate: " + obj_name)
        except Exception:
            pass

        result = obj.Delete()
        log(app, f"Delete {obj_name} 返回: {result}")
        return True
    except Exception as e:
        log(app, "删除对象失败: " + obj_name + "  " + repr(e))
        return False


def activate_or_create_study_case(app, case_name=STUDY_CASE_NAME):
    study_folder = get_project_folder_or_none(app, "study")

    if study_folder is None:
        raise RuntimeError("没有找到 Study Cases 文件夹 study。")

    cases = study_folder.GetContents("*.IntCase")
    target_case = None

    for case in cases:
        if case.loc_name == case_name:
            target_case = case
            break

    if target_case is None:
        if cases:
            target_case = cases[0]
            log(app, "没有找到指定 Study Case，使用已有 Study Case: " + target_case.loc_name)
        else:
            target_case = study_folder.CreateObject("IntCase", case_name)
            log(app, "新建 Study Case: " + target_case.loc_name)

    target_case.Activate()

    active_case = app.GetActiveStudyCase()
    if active_case is None:
        raise RuntimeError("Study Case 激活失败。")

    log(app, "已激活 Study Case: " + active_case.loc_name)
    return active_case


def get_or_create_grid(app):
    netdat = get_project_folder_or_none(app, "netdat")

    if netdat is None:
        raise RuntimeError("没有找到 PowerFactory Network Data 文件夹 netdat。")

    all_grids = netdat.GetContents("*.ElmNet")
    old_grids = []

    for g in all_grids:
        name = g.loc_name
        if name == GRID_NAME or name.startswith(GRID_NAME + "("):
            old_grids.append(g)

    log(app, "发现相关旧 ElmNet 数量: " + str(len(old_grids)))
    for g in old_grids:
        log(app, "  旧 ElmNet: " + g.loc_name)

    if DELETE_EXISTING_GRID:
        for g in old_grids:
            delete_object_if_possible(app, g)

        remaining = []
        for g in netdat.GetContents("*.ElmNet"):
            name = g.loc_name
            if name == GRID_NAME or name.startswith(GRID_NAME + "("):
                remaining.append(g)

        log(app, "删除后仍残留相关 ElmNet 数量: " + str(len(remaining)))
        for g in remaining:
            log(app, "  残留 ElmNet: " + g.loc_name)

        if remaining:
            raise RuntimeError(
                "旧 ElmNet 没有被成功删除。请在 Datenmanager 里手动删除残留 Grid，"
                "或者先取消 Study Case 对旧 Grid 的引用。"
            )

        grid = netdat.CreateObject("ElmNet", GRID_NAME)
        set_in_service(grid)
        log(app, "新建干净 ElmNet: " + grid.loc_name)
        return grid

    exact = netdat.GetContents(f"{GRID_NAME}.ElmNet")
    if exact:
        grid = exact[0]
        set_in_service(grid)
        log(app, "使用已有 ElmNet: " + grid.loc_name)
        return grid

    grid = netdat.CreateObject("ElmNet", GRID_NAME)
    set_in_service(grid)
    log(app, "新建 ElmNet: " + grid.loc_name)
    return grid


def deactivate_other_grids(app, target_grid_name):
    """
    Keep only the target ElmNet active in the current project.

    This avoids mixed load-flow calculations where objects from a previous
    imported grid, for example hour64, remain calculation-relevant together
    with the current 2030 autumn grid.
    """

    netdat = get_project_folder_or_none(app, "netdat")
    if netdat is None:
        log(app, "没有找到 netdat，无法取消激活其他 Grid。")
        return

    all_grids = netdat.GetContents("*.ElmNet") or []
    deactivated = 0

    for grid in all_grids:
        try:
            grid_name = grid.loc_name
        except Exception:
            continue

        if grid_name == target_grid_name:
            continue

        try:
            grid.Deactivate()
            deactivated += 1
            log(app, "已 Deactivate 其他 ElmNet: " + grid_name)
        except Exception as e:
            log(app, "Deactivate 其他 ElmNet 失败: " + grid_name + "  " + repr(e))

    log(app, "其他 ElmNet Deactivate 数量: " + str(deactivated))


def create_cubicle(term, obj_name):
    cub_name = "cub_" + safe_name(obj_name)

    existing = term.GetContents(cub_name + ".StaCubic")
    if existing:
        cub = existing[0]
        set_in_service(cub)
        return cub

    cub = term.CreateObject("StaCubic", cub_name)
    set_in_service(cub)
    return cub


def get_or_create_line_type(app, type_folder, type_name, voltage_kv, r_ohm_per_km, x_ohm_per_km, rated_mva, cline_uF_per_km=0.0, s_max_pu=1.0):
    type_name = safe_name(type_name)

    existing = type_folder.GetContents(type_name + ".TypLne")
    if existing:
        typ = existing[0]
    else:
        typ = type_folder.CreateObject("TypLne", type_name)
        log(app, "新建线路类型: " + type_name)

    typ.uline = voltage_kv
    typ.rline = r_ohm_per_km
    typ.xline = x_ohm_per_km

    # 重要：PowerFactory TypLne.sline 在这里按额定电流 kA 使用，不能直接写 MVA。
    # 由三相容量换算额定电流：I[kA] = S[MVA] / (sqrt(3) * U[kV])。
    # 如果 USE_PYPSA_S_MAX_PU_FOR_LINE_RATING=True，则把 PyPSA 的 s_max_pu 也作为安全容量折减。
    if USE_PYPSA_S_MAX_PU_FOR_LINE_RATING:
        effective_rated_mva = rated_mva * s_max_pu
    else:
        effective_rated_mva = rated_mva

    if voltage_kv > 0:
        rated_current_ka = effective_rated_mva / (math.sqrt(3.0) * voltage_kv)
    else:
        rated_current_ka = 1.0

    try:
        typ.sline = rated_current_ka
    except Exception:
        pass

    try:
        typ.desc = (
            "rated_mva_original=" + str(rated_mva)
            + "; s_max_pu=" + str(s_max_pu)
            + "; effective_rated_mva=" + str(effective_rated_mva)
            + "; rated_current_ka=" + str(rated_current_ka)
        )
    except Exception:
        pass

    try:
        typ.cline = cline_uF_per_km
    except Exception:
        pass

    try:
        typ.gline = 0.0
    except Exception:
        pass

    try:
        typ.frnom = 50.0
    except Exception:
        pass

    return typ


def get_line_connected_bus_set():
    line_path = os.path.join(PF_IMPORT_DIR, "pf_lines.csv")
    line_rows = read_csv_dict(line_path)

    connected = set()
    for row in line_rows:
        fb = safe_name(row.get("from_bus", ""))
        tb = safe_name(row.get("to_bus", ""))
        if fb:
            connected.add(fb)
        if tb:
            connected.add(tb)

    return connected


def configure_external_grid_settings(app, xnet, voltage_setpoint=1.0):
    try:
        xnet.usetp = voltage_setpoint
    except Exception:
        pass

    if not RELAX_EXTERNAL_GRID_Q_LIMITS:
        return

    qmin_attr = try_set_pf_attribute(
        xnet,
        [
            "q_min", "qmin", "Qmin", "Q_min",
            "cQ_min", "cQmin", "qgmin", "qg_min",
            "Qmin_uc", "qmin_uc", "minQ", "MinQ",
        ],
        -EXTERNAL_GRID_Q_LIMIT_MVAR,
    )
    qmax_attr = try_set_pf_attribute(
        xnet,
        [
            "q_max", "qmax", "Qmax", "Q_max",
            "cQ_max", "cQmax", "qgmax", "qg_max",
            "Qmax_uc", "qmax_uc", "maxQ", "MaxQ",
        ],
        EXTERNAL_GRID_Q_LIMIT_MVAR,
    )

    try:
        xnet.desc = (
            "External grid used as island reference/slack"
            + "; relaxed_qmin_attr=" + str(qmin_attr)
            + "; relaxed_qmax_attr=" + str(qmax_attr)
            + "; q_limit_mvar=" + str(EXTERNAL_GRID_Q_LIMIT_MVAR)
        )
    except Exception:
        pass


def create_or_update_external_grid_at_bus(app, grid, terminals, bus_name, voltage_setpoint=1.0):
    bus_name = safe_name(bus_name)

    if bus_name not in terminals:
        log(app, "无法创建 required slack，找不到 bus: " + bus_name)
        return None

    xnet_name = "slack_" + bus_name
    existing = grid.GetContents(xnet_name + ".ElmXnet")

    if existing:
        xnet = existing[0]
    else:
        xnet = grid.CreateObject("ElmXnet", xnet_name)
        log(app, "新建 required slack / ElmXnet: " + xnet_name)

    cub = create_cubicle(terminals[bus_name], xnet_name)
    xnet.bus1 = cub

    configure_external_grid_settings(app, xnet, voltage_setpoint)

    set_in_service(xnet)
    set_in_service(cub)

    return xnet


def ensure_required_external_grids(app, grid, terminals):
    if not REQUIRED_SLACK_BUSES:
        return

    log(app, "确保 required slack buses 存在: " + str(REQUIRED_SLACK_BUSES))

    for bus_name in REQUIRED_SLACK_BUSES:
        create_or_update_external_grid_at_bus(app, grid, terminals, bus_name, 1.0)


def ensure_external_grid(app, grid, terminals, slack_bus_name=DEFAULT_SLACK_BUS):
    existing_xnets = grid.GetContents("*.ElmXnet")

    if existing_xnets:
        for xnet in existing_xnets:
            configure_external_grid_settings(app, xnet, 1.0)
            set_in_service(xnet)
        log(app, "Grid 内已有 ElmXnet: " + str([x.loc_name for x in existing_xnets]))
        return existing_xnets[0]

    slack_bus_name = safe_name(slack_bus_name)

    if slack_bus_name not in terminals:
        log(app, "指定 slack bus 不存在: " + slack_bus_name)
        log(app, "可用 AC bus 示例:")
        for key in list(terminals.keys())[:30]:
            log(app, " - " + key)
        raise RuntimeError("无法创建 ElmXnet，因为找不到 bus: " + slack_bus_name)

    log(app, "没有找到 ElmXnet，正在强制创建 external grid at: " + slack_bus_name)

    xnet = create_or_update_external_grid_at_bus(app, grid, terminals, slack_bus_name, 1.0)

    log(app, "已创建 ElmXnet: " + xnet.loc_name + " at bus " + slack_bus_name)
    return xnet


def print_power_balance(app, loads, gens):
    total_load_p = 0.0
    total_load_q = 0.0
    total_gen_p = 0.0
    total_gen_q = 0.0

    for load in loads or []:
        if not is_in_service(load):
            continue
        try:
            total_load_p += float(load.plini)
            total_load_q += float(load.qlini)
        except Exception:
            pass

    for gen in gens or []:
        if not is_in_service(gen):
            continue
        try:
            total_gen_p += float(gen.pgini)
            total_gen_q += float(gen.qgini)
        except Exception:
            pass

    log(app, "")
    log(app, "功率统计:")
    log(app, "  Total Load P [MW]: " + str(round(total_load_p, 6)))
    log(app, "  Total Load Q [Mvar]: " + str(round(total_load_q, 6)))
    log(app, "  Total Gen P [MW]: " + str(round(total_gen_p, 6)))
    log(app, "  Total Gen Q [Mvar]: " + str(round(total_gen_q, 6)))
    log(app, "  Gen - Load P before External Grid [MW]: " + str(round(total_gen_p - total_load_p, 6)))
    log(app, "  Gen - Load Q before External Grid [Mvar]: " + str(round(total_gen_q - total_load_q, 6)))


def inspect_xnets(app, grid):
    log(app, "")
    log(app, "运行潮流前检查 ElmXnet:")

    grid_xnets = grid.GetContents("*.ElmXnet")
    log(app, "  Grid 内 ElmXnet: " + str(len(grid_xnets)))

    for x in grid_xnets:
        log(app, "  ElmXnet: " + x.loc_name)

        try:
            log(app, "    outserv = " + str(x.outserv))
        except Exception:
            pass

        try:
            log(app, "    bus1 = " + str(x.bus1))
        except Exception:
            pass

        try:
            log(app, "    usetp = " + str(x.usetp))
        except Exception:
            pass

    calc_xnets = app.GetCalcRelevantObjects("*.ElmXnet")
    log(app, "  Calc relevant ElmXnet: " + str(len(calc_xnets) if calc_xnets else 0))


def run_dc_load_flow(app):
    ldf = app.GetFromStudyCase("ComLdf")
    if ldf is None:
        raise RuntimeError("没有找到 ComLdf。")

    ldf.iopt_net = 1

    log(app, "")
    log(app, "正在运行 DC Load Flow...")
    result = ldf.Execute()

    log(app, "DC Load Flow 返回值: " + str(result))

    if result == 0:
        log(app, "DC Load Flow 成功。")
    else:
        log(app, "DC Load Flow 失败。请查看 Output Window / Ausgabefenster 中的红色错误。")

    return result


def inspect_distributed_slack_settings(app, ldf):
    """读取可能与 Verteilter Slack 有关的 ComLdf 属性，不修改其设置。"""
    log(app, "")
    log(app, "检查 ComLdf / Verteilter Slack 设置:")

    # 属性名称随 PowerFactory 版本变化；只报告当前版本确实存在的字段。
    candidates = [
        "iopt_pq", "iopt_slack", "iopt_dslack", "iopt_bal",
        "iopt_apdist", "iopt_disp", "iPbalancing", "slackMethod",
    ]
    found = []

    for attr in candidates:
        try:
            value = ldf.GetAttribute(attr)
            if value is None:
                continue
        except Exception:
            try:
                value = getattr(ldf, attr)
            except Exception:
                continue

        try:
            description = ldf.GetAttributeDescription(attr)
        except Exception:
            description = ""

        log(app, "  " + attr + " = " + str(value) + "; " + str(description))
        found.append((attr, value, description))

    if not found:
        log(app, "  未在候选字段中找到设置；这不等于 Verteilter Slack 未开启。")
        log(app, "  请结合下面的发电机 delta_P 结果判断是否实际发生分摊。")

    return found


def capture_generator_active_power_schedule(app):
    """在潮流前保存 ElmGenstat 的计划有功 pgini。"""
    schedules = []
    for gen in app.GetCalcRelevantObjects("*.ElmGenstat") or []:
        if not is_in_service(gen):
            continue
        try:
            p_schedule = float(gen.pgini)
        except Exception:
            continue
        try:
            bus = cubicle_to_terminal_name(gen.bus1)
        except Exception:
            bus = ""
        schedules.append({
            "object": gen,
            "name": gen.loc_name,
            "bus": bus,
            "p_schedule_mw": p_schedule,
        })
    return schedules


def analyse_distributed_slack_result(app, schedules, export_dir):
    """比较计划有功和潮流结果，并导出实际的 Verteilter Slack 分摊。"""
    rows = []
    raw_values = []

    for item in schedules:
        p_raw = get_result(item["object"], ["m:P:bus1", "m:Psum:bus1", "m:P"])
        try:
            p_raw = float(p_raw)
        except Exception:
            continue
        raw_values.append((item, p_raw))

    # ElmGenstat 端口结果的符号约定可能随模型/版本不同；选择总体上最接近
    # pgini 的方向，并在 CSV 中保留原始结果，便于人工复核。
    direct_error = sum(abs(p_raw - item["p_schedule_mw"]) for item, p_raw in raw_values)
    reverse_error = sum(abs(-p_raw - item["p_schedule_mw"]) for item, p_raw in raw_values)
    reverse_sign = reverse_error < direct_error

    for item, p_raw in raw_values:
        p_result = -p_raw if reverse_sign else p_raw
        delta_p = p_result - item["p_schedule_mw"]
        rows.append({
            "name": item["name"],
            "bus": item["bus"],
            "p_schedule_mw": item["p_schedule_mw"],
            "p_result_raw_mw": p_raw,
            "result_sign_reversed": int(reverse_sign),
            "p_result_mw": p_result,
            "delta_p_mw": delta_p,
            "participates_observed": int(abs(delta_p) >= DISTRIBUTED_SLACK_DELTA_P_TOLERANCE_MW),
            "observed_share": 0.0,
        })

    active_rows = [row for row in rows if row["participates_observed"] == 1]
    share_denominator = sum(abs(row["delta_p_mw"]) for row in active_rows)
    if share_denominator > 0.0:
        for row in active_rows:
            row["observed_share"] = abs(row["delta_p_mw"]) / share_denominator

    rows.sort(key=lambda row: abs(row["delta_p_mw"]), reverse=True)
    output_path = os.path.join(export_dir, "distributed_slack_results.csv")
    write_csv(output_path, [
        "name", "bus", "p_schedule_mw", "p_result_raw_mw",
        "result_sign_reversed", "p_result_mw", "delta_p_mw",
        "participates_observed", "observed_share",
    ], rows)

    log(app, "")
    log(app, "Verteilter Slack 结果诊断:")
    log(app, "  结果符号是否自动反转: " + str(reverse_sign))
    log(app, "  |delta_P| >= " + str(DISTRIBUTED_SLACK_DELTA_P_TOLERANCE_MW)
        + " MW 的 ElmGenstat 数量: " + str(len(active_rows)))
    log(app, "  诊断文件: " + output_path)
    for row in rows[:20]:
        if row["participates_observed"] != 1:
            continue
        log(app, "  " + row["name"]
            + ": P_schedule=" + str(round(row["p_schedule_mw"], 6))
            + " MW, P_result=" + str(round(row["p_result_mw"], 6))
            + " MW, delta_P=" + str(round(row["delta_p_mw"], 6))
            + " MW, share=" + str(round(100.0 * row["observed_share"], 3)) + "%")

    if not active_rows:
        log(app, "  未观察到明显有功分摊。原始工况可能几乎平衡，不能仅据此断定功能未开启。")
    elif len(active_rows) == 1:
        log(app, "  仅观察到一个 ElmGenstat 改变有功，尚不能证明多机 Distributed Slack 生效。")
    else:
        log(app, "  多个 ElmGenstat 的实际有功偏离计划值，观察到了分布式平衡效果。")

    return rows


def run_ac_load_flow(app):
    ldf = app.GetFromStudyCase("ComLdf")
    if ldf is None:
        raise RuntimeError("没有找到 ComLdf。")

    # 0 通常表示 AC Load Flow
    ldf.iopt_net = 0

    # 尝试关闭一些会让初步计算更复杂的控制选项。
    # 对发电机 Q 上下限，优先尝试开启限制检查；若属性不存在则忽略。
    for attr, value in [
        ("iopt_lim", 1),
        ("iopt_at", 0),
        ("iopt_asht", 0),
        ("iopt_trsh", 0),
        ("iopt_tap", 0),
        ("iopt_shunt", 0),
    ]:
        try:
            setattr(ldf, attr, value)
        except Exception:
            pass

    generator_schedules = []
    if ENABLE_DISTRIBUTED_SLACK_DIAGNOSTICS:
        inspect_distributed_slack_settings(app, ldf)
        generator_schedules = capture_generator_active_power_schedule(app)
        log(app, "潮流前已记录 ElmGenstat 计划出力: " + str(len(generator_schedules)))

    log(app, "")
    log(app, "正在运行 AC Load Flow...")
    result = ldf.Execute()

    log(app, "AC Load Flow 返回值: " + str(result))

    if result == 0:
        log(app, "AC Load Flow 成功。")
        if ENABLE_DISTRIBUTED_SLACK_DIAGNOSTICS:
            analyse_distributed_slack_result(app, generator_schedules, RESULT_EXPORT_DIR)
    else:
        log(app, "AC Load Flow 失败。请查看 Output Window / Ausgabefenster 中的红色错误。")

    return result


def set_first_existing_attribute(obj, candidates, value):
    """
    尝试给 PowerFactory 对象写入属性。
    返回成功写入的属性名；如果全部失败，返回空字符串。
    """
    for attr in candidates:
        try:
            setattr(obj, attr, value)
            return attr
        except Exception:
            pass
    return ""


def get_first_existing_attribute(obj, candidates):
    """
    尝试读取 PowerFactory 对象属性。
    返回 (属性名, 值)。失败则返回 ("", None)。
    """
    for attr in candidates:
        try:
            value = getattr(obj, attr)
            return attr, value
        except Exception:
            pass
    return "", None


def is_hvdc_equivalent_row(row):
    carrier = str(row.get("carrier", "")).strip().upper()
    name = str(row.get("name", "")).strip().lower()
    original_name = str(row.get("original_name", "")).strip().lower()

    if carrier in ["HVDC", "DC"]:
        return True
    if name.startswith("hvdc_"):
        return True
    if "hvdc" in original_name:
        return True

    return False


def is_hvdc_q_capability_device(row):
    value = str(row.get("_hvdc_qcap_device", "")).strip()
    if value == "1":
        return True

    name = str(row.get("name", "")).strip().lower()
    return name.startswith("hvdc_qcap_")


def has_csv_value(row, key):
    return str(row.get(key, "")).strip() != ""


def hvdc_capability_mode_enabled():
    return str(HVDC_Q_SUPPORT_MODE).strip().upper() == "CAPABILITY"


def configure_generator_q_capability(app, gen, row, p_mw, p_nom_mw):
    """
    根据 CSV 中的 q_min_mvar / q_max_mvar / pf_control_mode 设置 ElmGenstat。

    说明：PowerFactory 不同版本、不同对象模型的属性名可能不同。
    所以这里会尝试多个常见候选属性名，并把成功写入的属性名返回给日志统计。
    """

    if not ENABLE_GENERATOR_Q_CAPABILITY:
        return {
            "mode": "DISABLED",
            "qmin_attr": "",
            "qmax_attr": "",
            "control_attr": "",
            "control_value": "",
            "usetp_attr": "",
        }

    is_hvdc = is_hvdc_equivalent_row(row)
    is_hvdc_qcap = is_hvdc_q_capability_device(row)
    pf_control_mode = str(row.get("pf_control_mode", row.get("control_original", "PQ"))).strip().upper()

    hvdc_mode = str(HVDC_Q_SUPPORT_MODE).strip().upper()

    if is_hvdc_qcap and hvdc_mode == "CAPABILITY":
        pf_control_mode = str(HVDC_Q_CAPABILITY_CONTROL_MODE).strip().upper()
        q_limit = HVDC_Q_SUPPORT_RATIO * max(abs(p_nom_mw), abs(p_mw), 1.0)
        q_min_mvar = -q_limit
        q_max_mvar = q_limit
    elif is_hvdc and hvdc_mode == "CAPABILITY":
        # HVDC active-power equivalents stay PQ. Reactive control is handled by
        # one aggregated qcap device per bus, avoiding several elements regulating U.
        pf_control_mode = "PQ"
        q_min_mvar = 0.0
        q_max_mvar = 0.0
    elif (
        is_hvdc
        and LOCK_HVDC_GENERATOR_Q_TO_CSV
        and not has_csv_value(row, "q_min_mvar")
        and not has_csv_value(row, "q_max_mvar")
    ):
        pf_control_mode = "PQ"
        q_csv = to_float(row.get("q_mvar"), 0.0)
        q_min_mvar = q_csv
        q_max_mvar = q_csv
    else:
        q_min_mvar = to_float(row.get("q_min_mvar"), -DEFAULT_Q_RATIO * max(abs(p_nom_mw), abs(p_mw), 1.0))
        q_max_mvar = to_float(row.get("q_max_mvar"), DEFAULT_Q_RATIO * max(abs(p_nom_mw), abs(p_mw), 1.0))

    if q_min_mvar > q_max_mvar:
        q_min_mvar, q_max_mvar = q_max_mvar, q_min_mvar

    # 写入无功上下限。候选名包含常见 ElmGenstat / generator 字段名。
    qmin_attr = set_first_existing_attribute(
        gen,
        [
            "q_min", "qmin", "Qmin", "Q_min",
            "cQ_min", "cQmin", "qgmin", "qg_min",
        ],
        q_min_mvar,
    )

    qmax_attr = set_first_existing_attribute(
        gen,
        [
            "q_max", "qmax", "Qmax", "Q_max",
            "cQ_max", "cQmax", "qgmax", "qg_max",
        ],
        q_max_mvar,
    )

    # 电压设定值。
    usetp = to_float(row.get("voltage_setpoint", row.get("voltage_setpoint_pu", 1.0)), 1.0)
    usetp_attr = set_first_existing_attribute(gen, ["usetp", "usetp0", "vsetp", "Vsetp"], usetp)

    control_attr = ""
    control_value = ""

    if ENABLE_GENERATOR_PV_CONTROL and pf_control_mode == "PV":
        control_trials = [
            ("av_mode", "constv"),
            ("av_mode", "ConstV"),
            ("av_mode", 1),
            ("i_ctrl", 1),
            ("iopt_ctrl", 1),
            ("ctrl", 1),
            ("mode_inp", "V"),
            ("mode_inp", "PV"),
            ("iopt_pq", 1),
            ("iopt_mode", 1),
        ]
    else:
        control_trials = [
            ("av_mode", "constq"),
            ("av_mode", "ConstQ"),
            ("av_mode", 0),
            ("i_ctrl", 0),
            ("iopt_ctrl", 0),
            ("ctrl", 0),
            ("mode_inp", "PQ"),
            ("iopt_pq", 0),
            ("iopt_mode", 0),
        ]

    for attr, value in control_trials:
        try:
            setattr(gen, attr, value)
            control_attr = attr
            control_value = str(value)
            break
        except Exception:
            pass

    return {
        "mode": pf_control_mode,
        "qmin_attr": qmin_attr,
        "qmax_attr": qmax_attr,
        "control_attr": control_attr,
        "control_value": control_value,
        "usetp_attr": usetp_attr,
        "q_min_mvar": q_min_mvar,
        "q_max_mvar": q_max_mvar,
    }


def read_optional_csv_dict(app, path, label):
    if not os.path.isfile(path):
        log(app, "未找到 " + label + "，跳过。路径: " + path)
        return []

    rows = read_csv_dict(path)
    log(app, "读取 " + label + ": " + str(len(rows)) + " 行")
    return rows


def import_load_rows_into_grid(app, grid, terminals, load_rows, source_label):
    created_loads = 0
    updated_loads = 0
    skipped_loads = 0

    for row in load_rows:
        raw_name = safe_name(row.get("name", ""))
        name = LOAD_NAME_PREFIX + raw_name
        bus = safe_name(row.get("bus", ""))

        if not raw_name:
            skipped_loads += 1
            continue

        if bus not in terminals:
            log(app, "跳过负荷，找不到 AC bus: " + raw_name + "  bus=" + bus)
            skipped_loads += 1
            continue

        p_mw = to_float(row.get("p_mw"), 0.0)
        q_mvar = to_float(row.get("q_mvar"), 0.0)
        if is_hvdc_equivalent_row(row) and hvdc_capability_mode_enabled():
            q_mvar = 0.0

        existing = grid.GetContents(name + ".ElmLod")

        if existing:
            load = existing[0]
            updated_loads += 1
        else:
            load = grid.CreateObject("ElmLod", name)
            created_loads += 1

        cub = create_cubicle(terminals[bus], name)

        load.bus1 = cub
        load.plini = p_mw
        load.qlini = q_mvar

        try:
            load.desc = (
                "source_csv=" + source_label
                + "; original_name=" + str(row.get("original_name", ""))
                + "; carrier=" + str(row.get("carrier", ""))
            )
        except Exception:
            pass

        set_in_service(load)
        set_in_service(cub)

    log(app, "ElmLod 导入完成 (" + source_label + "):")
    log(app, "  新建: " + str(created_loads))
    log(app, "  更新: " + str(updated_loads))
    log(app, "  跳过: " + str(skipped_loads))

    return {
        "created": created_loads,
        "updated": updated_loads,
        "skipped": skipped_loads,
    }


def import_generator_rows_into_grid(app, grid, terminals, gen_rows, source_label):
    created_gens = 0
    updated_gens = 0
    skipped_gens = 0
    hvdc_gens = 0

    for i, row in enumerate(gen_rows, start=1):
        raw_name = safe_name(row.get("name", ""))
        name = GEN_NAME_PREFIX + raw_name
        bus = safe_name(row.get("bus", ""))

        if not raw_name:
            skipped_gens += 1
            continue

        if bus not in terminals:
            log(app, "跳过发电机，找不到 AC bus: " + raw_name + "  bus=" + bus)
            skipped_gens += 1
            continue

        is_hvdc = is_hvdc_equivalent_row(row)
        if is_hvdc:
            hvdc_gens += 1

        p_mw = to_float(row.get("p_mw"), 0.0)
        q_mvar = to_float(row.get("q_mvar"), 0.0)
        p_nom_mw = to_float(row.get("p_nom_mw"), max(abs(p_mw), 1.0))

        if p_nom_mw <= 0:
            p_nom_mw = max(abs(p_mw), 1.0)

        if is_hvdc and hvdc_capability_mode_enabled():
            q_mvar = 0.0

        if FORCE_GENERATOR_INITIAL_Q_BY_COSPHI and not is_hvdc:
            q_mvar = FORCE_GENERATOR_Q_SIGN * DEFAULT_Q_RATIO * max(abs(p_nom_mw), abs(p_mw), 1.0)

        existing = grid.GetContents(name + ".ElmGenstat")

        if existing:
            gen = existing[0]
            updated_gens += 1
        else:
            gen = grid.CreateObject("ElmGenstat", name)
            created_gens += 1

        cub = create_cubicle(terminals[bus], name)

        gen.bus1 = cub
        gen.pgini = p_mw
        gen.qgini = q_mvar

        try:
            gen.sgn = max(p_nom_mw, abs(p_mw), 1.0)
        except Exception:
            pass

        try:
            gen.usetp = to_float(row.get("voltage_setpoint", row.get("voltage_setpoint_pu", 1.0)), 1.0)
        except Exception:
            pass

        q_cfg = configure_generator_q_capability(app, gen, row, p_mw, p_nom_mw)

        try:
            gen.desc = (
                "source_csv=" + source_label
                + "; carrier=" + str(row.get("carrier", ""))
                + "; original_name=" + str(row.get("original_name", ""))
                + "; pf_control_mode=" + str(q_cfg.get("mode", ""))
                + "; q_min_mvar=" + str(round(float(q_cfg.get("q_min_mvar", q_mvar)), 6))
                + "; q_max_mvar=" + str(round(float(q_cfg.get("q_max_mvar", q_mvar)), 6))
            )
        except Exception:
            pass

        set_in_service(gen)
        set_in_service(cub)

        if i % 50 == 0:
            log(app, "  已导入发电机 " + str(i) + "/" + str(len(gen_rows)) + " (" + source_label + ")")

    log(app, "ElmGenstat 导入完成 (" + source_label + "):")
    log(app, "  新建: " + str(created_gens))
    log(app, "  更新: " + str(updated_gens))
    log(app, "  跳过: " + str(skipped_gens))
    log(app, "  其中 HVDC 等效发电机行: " + str(hvdc_gens))

    return {
        "created": created_gens,
        "updated": updated_gens,
        "skipped": skipped_gens,
        "hvdc": hvdc_gens,
    }


def read_hvdc_p_nom_by_original_name(app):
    summary_path = os.path.join(PF_IMPORT_DIR, HVDC_SUMMARY_FILE)
    rows = read_optional_csv_dict(app, summary_path, HVDC_SUMMARY_FILE)
    p_nom_by_original_name = {}

    for row in rows:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        p_nom_by_original_name[name] = abs(to_float(row.get("p_nom_mw"), 0.0))

    return p_nom_by_original_name


def cleanup_old_hvdc_q_support_devices(app, grid):
    existing_gens = grid.GetContents("*.ElmGenstat") or []
    deleted = 0

    for gen in existing_gens:
        name = safe_name(gen.loc_name)
        if name.startswith(GEN_NAME_PREFIX + "hvdc_qcap_"):
            if delete_object_if_possible(app, gen):
                deleted += 1

    if deleted:
        log(app, "已删除旧 HVDC qcap devices: " + str(deleted))


def force_existing_non_hvdc_generators_to_pq_on_buses(app, grid, target_buses):
    """
    Avoid PowerFactory errors of the form "Mehr als ein Element regelt U".

    When an HVDC qcap device is used as PV controller at a bus, any existing
    non-HVDC generator on the same bus must not regulate voltage as well.
    """

    target_buses = set(safe_name(bus) for bus in (target_buses or []))
    if not target_buses:
        return

    existing_gens = grid.GetContents("*.ElmGenstat") or []
    changed = 0

    pq_control_trials = [
        ("av_mode", "constq"),
        ("av_mode", "ConstQ"),
        ("av_mode", 0),
        ("i_ctrl", 0),
        ("iopt_ctrl", 0),
        ("ctrl", 0),
        ("mode_inp", "PQ"),
        ("iopt_pq", 0),
        ("iopt_mode", 0),
    ]

    for gen in existing_gens:
        gen_name = safe_name(gen.loc_name)
        gen_name_lower = gen_name.lower()

        if "hvdc" in gen_name_lower:
            continue

        try:
            bus_name = safe_name(cubicle_to_terminal_name(gen.bus1))
        except Exception:
            bus_name = ""

        if bus_name not in target_buses:
            continue

        written_controls = []

        for attr, value in pq_control_trials:
            try:
                setattr(gen, attr, value)
                written_controls.append(attr + "=" + str(value))
            except Exception:
                pass

        try:
            old_desc = str(gen.desc)
        except Exception:
            old_desc = ""

        try:
            gen.desc = (
                old_desc
                + "; forced_to_PQ_because_HVDC_qcap_controls_bus=1"
                + "; pq_control_attrs="
                + ",".join(written_controls)
            )
        except Exception:
            pass

        changed += 1
        log(
            app,
            "  HVDC PV priority: set existing generator to PQ at "
            + bus_name
            + ": "
            + gen.loc_name
            + " via "
            + ",".join(written_controls),
        )

    log(app, "HVDC PV priority: forced non-HVDC generators to PQ: " + str(changed))


def create_hvdc_q_support_devices_by_bus(app, grid, terminals, hvdc_gen_rows, hvdc_load_rows):
    if not CREATE_HVDC_Q_SUPPORT_DEVICE_AT_LOAD_END:
        return

    if not hvdc_capability_mode_enabled():
        return

    p_nom_by_original_name = read_hvdc_p_nom_by_original_name(app)
    qcap_by_bus = {}
    slack_buses = set(safe_name(bus) for bus in REQUIRED_SLACK_BUSES)

    for row in (hvdc_gen_rows or []) + (hvdc_load_rows or []):
        if not is_hvdc_equivalent_row(row):
            continue

        bus = safe_name(row.get("bus", ""))
        if not bus or bus not in terminals:
            continue

        if bus in slack_buses:
            log(app, "跳过 slack bus 上的 HVDC qcap PV controller: " + bus)
            continue

        original_name = str(row.get("original_name", "")).strip()
        p_nom_mw = to_float(row.get("p_nom_mw"), 0.0)
        if p_nom_mw <= 0.0:
            p_nom_mw = p_nom_by_original_name.get(original_name, 0.0)
        if p_nom_mw <= 0.0:
            p_nom_mw = max(abs(to_float(row.get("p_mw"), 0.0)), 1.0)

        if bus not in qcap_by_bus:
            qcap_by_bus[bus] = {
                "bus": bus,
                "p_nom_mw": 0.0,
                "count": 0,
            }

        qcap_by_bus[bus]["p_nom_mw"] += p_nom_mw
        qcap_by_bus[bus]["count"] += 1

    if not qcap_by_bus:
        log(app, "没有需要创建的聚合 HVDC Q support devices。")
        return

    cleanup_old_hvdc_q_support_devices(app, grid)
    if str(HVDC_Q_CAPABILITY_CONTROL_MODE).strip().upper() == "PV":
        force_existing_non_hvdc_generators_to_pq_on_buses(app, grid, qcap_by_bus.keys())

    q_support_rows = []
    for bus in sorted(qcap_by_bus):
        info = qcap_by_bus[bus]
        q_support_rows.append({
            "name": "hvdc_qcap_" + bus,
            "bus": bus,
            "carrier": "HVDC",
            "p_mw": "0.0",
            "q_mvar": "0.0",
            "p_nom_mw": str(info["p_nom_mw"]),
            "voltage_setpoint": "1.0",
            "pf_control_mode": HVDC_Q_CAPABILITY_CONTROL_MODE,
            "control_original": HVDC_Q_CAPABILITY_CONTROL_MODE,
            "original_name": "aggregated_hvdc_qcap_at_" + bus,
            "_hvdc_qcap_device": "1",
        })

    log(app, "创建聚合 HVDC Q support devices: " + str(len(q_support_rows)))
    for bus in sorted(qcap_by_bus):
        info = qcap_by_bus[bus]
        q_limit = HVDC_Q_SUPPORT_RATIO * info["p_nom_mw"]
        log(app, "  " + bus + ": links=" + str(info["count"]) + ", q_limit_mvar=±" + str(round(q_limit, 6)))

    import_generator_rows_into_grid(app, grid, terminals, q_support_rows, "HVDC aggregated Q support")


def get_generator_q_range(gen):
    _, qmin = get_first_existing_attribute(
        gen, ["q_min", "qmin", "Qmin", "Q_min", "cQ_min", "cQmin", "qgmin", "qg_min"]
    )
    _, qmax = get_first_existing_attribute(
        gen, ["q_max", "qmax", "Qmax", "Q_max", "cQ_max", "cQmax", "qgmax", "qg_max"]
    )
    try:
        return float(qmin), float(qmax)
    except Exception:
        return None, None


def try_set_object_reference(obj, trials):
    """写入对象引用后回读，避免 PowerFactory 类型错误时仅记日志却不抛异常。"""
    for attr, value in trials:
        try:
            setattr(obj, attr, value)
        except Exception:
            try:
                obj.SetAttribute(attr, value)
            except Exception:
                continue
        try:
            written = obj.GetAttribute(attr)
        except Exception:
            try:
                written = getattr(obj, attr)
            except Exception:
                written = None
        if written is not None and written != "" and written != 0:
            return attr
    return ""


def create_station_controllers_by_bus(app, grid, terminals):
    """每个非 Slack bus 用一个 ElmStactrl 协调该 bus 上所有 Q-capable ElmGenstat。"""
    if not ENABLE_STATION_CONTROLLER_BY_BUS:
        return []
    for old in grid.GetContents("*.ElmStactrl") or []:
        if str(old.loc_name).startswith(STATION_CONTROLLER_NAME_PREFIX):
            delete_object_if_possible(app, old)

    slack_buses = set(safe_name(x) for x in REQUIRED_SLACK_BUSES)
    by_bus = {}
    for gen in grid.GetContents("*.ElmGenstat") or []:
        if not is_in_service(gen):
            continue
        try:
            bus = safe_name(cubicle_to_terminal_name(gen.bus1))
        except Exception:
            continue
        if not bus or bus not in terminals or bus in slack_buses:
            continue
        qmin, qmax = get_generator_q_range(gen)
        if qmin is None or qmax is None or qmax - qmin <= 1e-6:
            continue
        by_bus.setdefault(bus, []).append({"gen": gen, "qmin": qmin, "qmax": qmax})

    controllers, failures = [], []
    for bus in sorted(by_bus):
        participants = by_bus[bus]
        if len(participants) < STATION_CONTROLLER_MIN_PARTICIPANTS:
            continue
        name = STATION_CONTROLLER_NAME_PREFIX + bus
        ctrl = grid.CreateObject("ElmStactrl", name)
        if ctrl is None:
            failures.append(bus + ": ElmStactrl creation failed")
            continue

        # 已由 Spring 实测确认：rembar 必须直接引用 ElmTerm，不能传 StaCubic。
        bus_attr = try_set_object_reference(ctrl, [
            ("rembar", terminals[bus]),
            ("p_busbar", terminals[bus]),
            ("p_target", terminals[bus]),
        ])
        usetp_attr = try_set_pf_attribute(
            ctrl, ["usetp", "usetp0", "vsetp", "Vsetp"], STATION_CONTROLLER_U_SETPOINT
        )
        mode_attr = try_set_pf_attribute(ctrl, ["i_ctrl", "iopt_ctrl", "ctrl"], 0)
        set_in_service(ctrl)

        linked, unlinked, link_attrs = [], [], set()
        for item in participants:
            gen = item["gen"]
            # 机组不再独立 PV；ElmStactrl 是该母线唯一电压控制主体。
            for attr, value in [
                ("av_mode", "constq"), ("av_mode", "ConstQ"),
                ("i_ctrl", 0), ("iopt_ctrl", 0), ("ctrl", 0),
                ("mode_inp", "PQ"), ("iopt_pq", 0), ("iopt_mode", 0),
            ]:
                try:
                    setattr(gen, attr, value)
                    break
                except Exception:
                    pass
            link_attr = try_set_object_reference(gen, [
                ("c_pstac", ctrl), ("p_stactrl", ctrl), ("pstac", ctrl),
                ("stactrl", ctrl), ("pStactrl", ctrl),
            ])
            if link_attr:
                linked.append(gen.loc_name)
                link_attrs.add(link_attr)
            else:
                unlinked.append(gen.loc_name)

        try:
            ctrl.desc = (
                "controlled_bus=" + bus + "; bus_attr=" + bus_attr
                + "; usetp_attr=" + usetp_attr + "; mode_attr=" + mode_attr
                + "; linked_generators=" + str(len(linked))
            )
        except Exception:
            pass
        if not bus_attr or not usetp_attr or unlinked:
            failures.append(
                bus + ": bus_attr=" + str(bus_attr) + ", usetp_attr=" + str(usetp_attr)
                + ", linked=" + str(len(linked)) + ", unlinked=" + str(unlinked)
            )
            continue
        controllers.append(ctrl)
        log(app, "Station Controller " + name
            + ": generators=" + str(len(linked))
            + ", Qrange=[" + str(round(sum(x["qmin"] for x in participants), 6))
            + ", " + str(round(sum(x["qmax"] for x in participants), 6)) + "] Mvar"
            + ", bus_attr=" + bus_attr + ", gen_link_attr=" + ",".join(sorted(link_attrs)))

    if failures:
        for message in failures:
            log(app, "Station Controller 配置失败: " + message)
        raise RuntimeError(
            "Station Controller 未完整关联；请根据日志确认当前 PowerFactory 版本的 ElmStactrl/ElmGenstat 属性名。"
        )
    log(app, "Station Controller 创建完成: " + str(len(controllers)))
    return controllers


def log_hvdc_summary(app):
    if not IMPORT_HVDC_EQUIVALENTS:
        return

    summary_path = os.path.join(PF_IMPORT_DIR, HVDC_SUMMARY_FILE)
    rows = read_optional_csv_dict(app, summary_path, HVDC_SUMMARY_FILE)
    if not rows:
        return

    total_sent_mw = 0.0
    total_received_mw = 0.0
    total_loss_mw = 0.0

    for row in rows:
        total_sent_mw += to_float(row.get("sent_mw"), 0.0)
        total_received_mw += to_float(row.get("received_mw"), 0.0)
        total_loss_mw += to_float(row.get("loss_mw"), 0.0)

    log(app, "HVDC link 摘要:")
    log(app, "  link 数量: " + str(len(rows)))
    log(app, "  sent_mw 合计: " + str(round(total_sent_mw, 6)))
    log(app, "  received_mw 合计: " + str(round(total_received_mw, 6)))
    log(app, "  loss_mw 合计: " + str(round(total_loss_mw, 6)))


# ==============================
# 4. 结果读取与 CSV 导出函数
# ==============================

def get_result(obj, var_names):
    """
    尝试读取 PowerFactory 计算结果变量。
    不同版本 / 元件类型变量名可能略有不同，所以传入多个候选名。
    """
    for var in var_names:
        try:
            value = obj.GetAttribute(var)
            if value is not None:
                return value
        except Exception:
            pass
    return None


def value_to_text(value):
    if value is None:
        return ""
    try:
        return str(float(value))
    except Exception:
        return str(value)


def ensure_dir(path):
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def write_csv(path, fieldnames, rows):
    ensure_dir(os.path.dirname(path))

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def cubicle_to_terminal_name(cub):
    """尽量从 StaCubic 读取连接的母线名称。失败则返回 cubicle 字符串。"""
    try:
        parent = cub.GetParent()
        if parent is not None:
            return parent.loc_name
    except Exception:
        pass

    try:
        return str(cub)
    except Exception:
        return ""


def country_code_from_bus_name(bus_name):
    """
    Extract the country code from PyPSA-style bus names.

    Examples:
    DE0_0 -> DE
    AT0_0 -> AT
    DK1_0 -> DK
    """

    text = str(bus_name or "").strip().upper()
    letters = ""

    for ch in text:
        if ch.isalpha():
            letters += ch
        else:
            break

    if len(letters) >= 2:
        return letters[:2]

    return ""


def get_line_rated_capacity_mva(line):
    try:
        return math.sqrt(3.0) * float(line.typ_id.uline) * float(line.typ_id.sline)
    except Exception:
        return None


def get_line_loading_percent_from_results(line, rated_mva):
    if rated_mva is None or rated_mva <= 0:
        return None

    try:
        p1 = float(get_result(line, ["m:P:bus1", "m:Psum:bus1"]))
        q1 = float(get_result(line, ["m:Q:bus1", "m:Qsum:bus1"]))
        p2 = float(get_result(line, ["m:P:bus2", "m:Psum:bus2"]))
        q2 = float(get_result(line, ["m:Q:bus2", "m:Qsum:bus2"]))
        s1 = math.sqrt(p1 ** 2 + q1 ** 2)
        s2 = math.sqrt(p2 ** 2 + q2 ** 2)
        return max(s1, s2) / rated_mva * 100.0
    except Exception:
        try:
            return float(get_result(line, ["c:loading", "m:loading"]))
        except Exception:
            return None


def rounded_text(value, digits=3):
    if value is None:
        return ""

    try:
        return str(round(float(value), digits))
    except Exception:
        return str(value)


def print_german_interconnector_capacities(app, lines):
    rows = []
    totals_by_neighbor = {}

    for line in lines:
        try:
            bus1_name = cubicle_to_terminal_name(line.bus1)
        except Exception:
            bus1_name = ""

        try:
            bus2_name = cubicle_to_terminal_name(line.bus2)
        except Exception:
            bus2_name = ""

        country1 = country_code_from_bus_name(bus1_name)
        country2 = country_code_from_bus_name(bus2_name)

        if country1 == "DE" and country2 and country2 != "DE":
            neighbor = country2
        elif country2 == "DE" and country1 and country1 != "DE":
            neighbor = country1
        else:
            continue

        rated_mva = get_line_rated_capacity_mva(line)
        loading_percent = get_line_loading_percent_from_results(line, rated_mva)

        rows.append(
            {
                "neighbor": neighbor,
                "name": line.loc_name,
                "from_bus": bus1_name,
                "to_bus": bus2_name,
                "rated_mva": rated_mva,
                "loading_percent": loading_percent,
            }
        )

        if rated_mva is not None:
            totals_by_neighbor[neighbor] = totals_by_neighbor.get(neighbor, 0.0) + rated_mva

    rows.sort(key=lambda row: (row["neighbor"], row["from_bus"], row["to_bus"], row["name"]))

    log(app, "")
    log(app, "德国与相邻国家互联线容量（按线路额定电流换算）:")

    if not rows:
        log(app, "  未找到一端为 DE、另一端为相邻国家的 ElmLne。")
        return

    for row in rows:
        log(
            app,
            "  DE-"
            + row["neighbor"]
            + " | "
            + row["name"]
            + " | "
            + row["from_bus"]
            + " -> "
            + row["to_bus"]
            + " | capacity = "
            + rounded_text(row["rated_mva"], 3)
            + " MVA"
            + " | loading = "
            + rounded_text(row["loading_percent"], 3)
            + " %",
        )

    log(app, "")
    log(app, "德国互联线容量按邻国汇总:")

    for neighbor in sorted(totals_by_neighbor):
        log(
            app,
            "  DE-"
            + neighbor
            + " total capacity = "
            + rounded_text(totals_by_neighbor[neighbor], 3)
            + " MVA",
        )


def export_german_interconnector_capacity_csv(app, export_dir, line_rows):
    """导出德国—邻国跨境 AC 线路容量占比明细和逐国界汇总。"""
    names = {"AT":"Austria", "BE":"Belgium", "CH":"Switzerland", "CZ":"Czechia",
             "DK":"Denmark", "FR":"France", "LU":"Luxembourg", "NL":"Netherlands", "PL":"Poland"}
    details = []
    for row in line_rows:
        fb, tb = str(row.get("from_bus", "")), str(row.get("to_bus", ""))
        fc, tc = country_code_from_bus_name(fb), country_code_from_bus_name(tb)
        if fc == "DE" and tc in names:
            code, de_bus, other_bus, de_p = tc, fb, tb, to_float(row.get("p_from_mw"), 0.0)
        elif tc == "DE" and fc in names:
            code, de_bus, other_bus, de_p = fc, tb, fb, to_float(row.get("p_to_mw"), 0.0)
        else:
            continue
        cap = to_float(row.get("rated_mva_from_current"), 0.0)
        used = max(abs(to_float(row.get("apparent_from_mva"), 0.0)), abs(to_float(row.get("apparent_to_mva"), 0.0)))
        details.append({
            "neighbor_country_code":code, "neighbor_country":names[code], "line_name":row.get("name", ""),
            "germany_bus":de_bus, "neighbor_bus":other_bus, "rated_capacity_mva":cap,
            "used_apparent_power_mva":used, "capacity_utilization_percent":used/cap*100.0 if cap else 0.0,
            "net_export_from_germany_mw":de_p,
            "flow_direction":"Germany export" if de_p > 1e-9 else ("Germany import" if de_p < -1e-9 else "No active transfer"),
            "line_capacity_share_within_border_percent":0.0,
            "line_capacity_share_all_germany_borders_percent":0.0,
            "loading_percent_pf":to_float(row.get("loading_percent"), 0.0),
        })
    total = sum(x["rated_capacity_mva"] for x in details)
    caps = {}
    for x in details: caps[x["neighbor_country_code"]] = caps.get(x["neighbor_country_code"], 0.0) + x["rated_capacity_mva"]
    for x in details:
        border = caps[x["neighbor_country_code"]]
        x["line_capacity_share_within_border_percent"] = x["rated_capacity_mva"]/border*100.0 if border else 0.0
        x["line_capacity_share_all_germany_borders_percent"] = x["rated_capacity_mva"]/total*100.0 if total else 0.0
    summaries = []
    for code in sorted(caps):
        items = [x for x in details if x["neighbor_country_code"] == code]
        cap = sum(x["rated_capacity_mva"] for x in items)
        used = sum(x["used_apparent_power_mva"] for x in items)
        net = sum(x["net_export_from_germany_mw"] for x in items)
        summaries.append({
            "neighbor_country_code":code, "neighbor_country":names[code], "line_count":len(items),
            "total_rated_capacity_mva":cap, "total_used_apparent_power_mva":used,
            "capacity_weighted_utilization_percent":used/cap*100.0 if cap else 0.0,
            "maximum_line_utilization_percent":max([x["capacity_utilization_percent"] for x in items] or [0.0]),
            "net_export_from_germany_mw":net,
            "net_flow_direction":"Germany net export" if net > 1e-9 else ("Germany net import" if net < -1e-9 else "Balanced"),
            "border_capacity_share_all_germany_borders_percent":cap/total*100.0 if total else 0.0,
        })
    details.sort(key=lambda x:(x["neighbor_country_code"], -x["capacity_utilization_percent"], x["line_name"]))
    write_csv(os.path.join(export_dir, "germany_neighbor_line_capacity_detail.csv"), [
        "neighbor_country_code","neighbor_country","line_name","germany_bus","neighbor_bus",
        "rated_capacity_mva","used_apparent_power_mva","capacity_utilization_percent",
        "net_export_from_germany_mw","flow_direction","line_capacity_share_within_border_percent",
        "line_capacity_share_all_germany_borders_percent","loading_percent_pf"], details)
    write_csv(os.path.join(export_dir, "germany_neighbor_line_capacity_summary.csv"), [
        "neighbor_country_code","neighbor_country","line_count","total_rated_capacity_mva",
        "total_used_apparent_power_mva","capacity_weighted_utilization_percent",
        "maximum_line_utilization_percent","net_export_from_germany_mw","net_flow_direction",
        "border_capacity_share_all_germany_borders_percent"], summaries)
    log(app, "德国—邻国跨境容量 CSV: lines=" + str(len(details)) + ", borders=" + str(len(summaries)))
    return details, summaries


def export_load_flow_results_to_csv(app, export_dir):
    """
    导出完整 Load Flow 结果：
    - bus_results.csv
    - line_results.csv
    - slack_results.csv
    - load_results.csv
    - generator_results.csv
    """

    log_section(app, "步骤 13：导出 Load Flow 结果 CSV")

    ensure_dir(export_dir)

    terms = app.GetCalcRelevantObjects("*.ElmTerm") or []
    lines = app.GetCalcRelevantObjects("*.ElmLne") or []
    loads = app.GetCalcRelevantObjects("*.ElmLod") or []
    gens = app.GetCalcRelevantObjects("*.ElmGenstat") or []
    xnets = app.GetCalcRelevantObjects("*.ElmXnet") or []

    # ==============================
    # 1) Bus results
    # ==============================

    bus_rows = []

    for term in terms:
        u_pu = get_result(term, ["m:u", "m:Ul", "m:U"])
        angle_deg = get_result(term, ["m:phiu", "m:phiu1", "m:phi"])
        u_kv = get_result(term, ["m:U1", "m:Ubus1", "m:U"])

        try:
            uknom = term.uknom
        except Exception:
            uknom = ""

        try:
            outserv = term.outserv
        except Exception:
            outserv = ""

        # 同时尝试导出经纬度，方便检查是否写入成功
        lon_attr, lon_value = get_first_existing_attribute(
            term,
            [
                "GPSlon", "gpslon", "GPSLon", "GpsLon", "GPSlondeg", "gpslondeg",
                "longitude", "Longitude", "lon", "Lon", "x", "X",
                "Ostwert", "ostwert", "easting", "Easting", "east", "East",
            ],
        )
        lat_attr, lat_value = get_first_existing_attribute(
            term,
            [
                "GPSlat", "gpslat", "GPSLat", "GpsLat", "GPSlatdeg", "gpslatdeg",
                "latitude", "Latitude", "lat", "Lat", "y", "Y",
                "Nordwert", "nordwert", "northing", "Northing", "north", "North",
            ],
        )

        bus_rows.append({
            "name": term.loc_name,
            "uknom_kv": value_to_text(uknom),
            "u_pu": value_to_text(u_pu),
            "u_kv": value_to_text(u_kv),
            "angle_deg": value_to_text(angle_deg),
            "outserv": value_to_text(outserv),
            "longitude_attr": lon_attr,
            "longitude": value_to_text(lon_value),
            "latitude_attr": lat_attr,
            "latitude": value_to_text(lat_value),
        })

    write_csv(
        os.path.join(export_dir, "bus_results.csv"),
        [
            "name", "uknom_kv", "u_pu", "u_kv", "angle_deg", "outserv",
            "longitude_attr", "longitude", "latitude_attr", "latitude",
        ],
        bus_rows
    )

    # ==============================
    # 2) Line results
    # ==============================

    line_rows = []

    for line in lines:
        loading = get_result(line, ["c:loading", "m:loading"])
        p_bus1 = get_result(line, ["m:P:bus1", "m:Psum:bus1"])
        q_bus1 = get_result(line, ["m:Q:bus1", "m:Qsum:bus1"])
        p_bus2 = get_result(line, ["m:P:bus2", "m:Psum:bus2"])
        q_bus2 = get_result(line, ["m:Q:bus2", "m:Qsum:bus2"])
        i_bus1 = get_result(line, ["m:I:bus1", "m:I1:bus1"])
        i_bus2 = get_result(line, ["m:I:bus2", "m:I1:bus2"])

        try:
            length_km = line.dline
        except Exception:
            length_km = ""

        try:
            typ_name = line.typ_id.loc_name
        except Exception:
            typ_name = ""

        try:
            typ_sline_ka = line.typ_id.sline
        except Exception:
            typ_sline_ka = ""

        try:
            typ_voltage_kv = line.typ_id.uline
        except Exception:
            typ_voltage_kv = ""

        try:
            rated_mva_from_current = math.sqrt(3.0) * float(typ_voltage_kv) * float(typ_sline_ka)
        except Exception:
            rated_mva_from_current = ""

        try:
            apparent_from_mva = math.sqrt(float(p_bus1) ** 2 + float(q_bus1) ** 2)
        except Exception:
            apparent_from_mva = ""

        try:
            apparent_to_mva = math.sqrt(float(p_bus2) ** 2 + float(q_bus2) ** 2)
        except Exception:
            apparent_to_mva = ""

        try:
            loading_calc_percent = max(float(apparent_from_mva), float(apparent_to_mva)) / float(rated_mva_from_current) * 100.0
        except Exception:
            loading_calc_percent = ""

        try:
            bus1_name = cubicle_to_terminal_name(line.bus1)
        except Exception:
            bus1_name = ""

        try:
            bus2_name = cubicle_to_terminal_name(line.bus2)
        except Exception:
            bus2_name = ""

        try:
            outserv = line.outserv
        except Exception:
            outserv = ""

        line_rows.append({
            "name": line.loc_name,
            "from_bus": bus1_name,
            "to_bus": bus2_name,
            "type": typ_name,
            "rated_current_ka_pf": value_to_text(typ_sline_ka),
            "rated_mva_from_current": value_to_text(rated_mva_from_current),
            "apparent_from_mva": value_to_text(apparent_from_mva),
            "apparent_to_mva": value_to_text(apparent_to_mva),
            "loading_calc_percent": value_to_text(loading_calc_percent),
            "length_km": value_to_text(length_km),
            "p_from_mw": value_to_text(p_bus1),
            "q_from_mvar": value_to_text(q_bus1),
            "p_to_mw": value_to_text(p_bus2),
            "q_to_mvar": value_to_text(q_bus2),
            "i_from_ka": value_to_text(i_bus1),
            "i_to_ka": value_to_text(i_bus2),
            "loading_percent": value_to_text(loading),
            "outserv": value_to_text(outserv),
        })

    write_csv(
        os.path.join(export_dir, "line_results.csv"),
        [
            "name",
            "from_bus",
            "to_bus",
            "type",
            "rated_current_ka_pf",
            "rated_mva_from_current",
            "apparent_from_mva",
            "apparent_to_mva",
            "loading_calc_percent",
            "length_km",
            "p_from_mw",
            "q_from_mvar",
            "p_to_mw",
            "q_to_mvar",
            "i_from_ka",
            "i_to_ka",
            "loading_percent",
            "outserv",
        ],
        line_rows
    )

    germany_neighbor_detail_rows, germany_neighbor_summary_rows = (
        export_german_interconnector_capacity_csv(app, export_dir, line_rows)
    )

    # ==============================
    # 3) External Grid / Slack results
    # ==============================

    slack_rows = []

    for xnet in xnets:
        p = get_result(xnet, ["m:P:bus1", "m:Psum:bus1", "m:P"])
        q = get_result(xnet, ["m:Q:bus1", "m:Qsum:bus1", "m:Q"])

        try:
            bus1 = cubicle_to_terminal_name(xnet.bus1)
        except Exception:
            bus1 = ""

        try:
            usetp = xnet.usetp
        except Exception:
            usetp = ""

        try:
            outserv = xnet.outserv
        except Exception:
            outserv = ""

        slack_rows.append({
            "name": xnet.loc_name,
            "bus": bus1,
            "usetp_pu": value_to_text(usetp),
            "p_mw": value_to_text(p),
            "q_mvar": value_to_text(q),
            "outserv": value_to_text(outserv),
        })

    write_csv(
        os.path.join(export_dir, "slack_results.csv"),
        ["name", "bus", "usetp_pu", "p_mw", "q_mvar", "outserv"],
        slack_rows
    )

    # ==============================
    # 4) Load results
    # ==============================

    load_rows = []

    for load in loads:
        p = get_result(load, ["m:P:bus1", "m:Psum:bus1", "m:P"])
        q = get_result(load, ["m:Q:bus1", "m:Qsum:bus1", "m:Q"])

        try:
            plini = load.plini
        except Exception:
            plini = ""

        try:
            qlini = load.qlini
        except Exception:
            qlini = ""

        try:
            bus1 = cubicle_to_terminal_name(load.bus1)
        except Exception:
            bus1 = ""

        try:
            outserv = load.outserv
        except Exception:
            outserv = ""

        load_rows.append({
            "name": load.loc_name,
            "bus": bus1,
            "plini_mw": value_to_text(plini),
            "qlini_mvar": value_to_text(qlini),
            "p_result_mw": value_to_text(p),
            "q_result_mvar": value_to_text(q),
            "outserv": value_to_text(outserv),
        })

    write_csv(
        os.path.join(export_dir, "load_results.csv"),
        ["name", "bus", "plini_mw", "qlini_mvar", "p_result_mw", "q_result_mvar", "outserv"],
        load_rows
    )

    # ==============================
    # 5) Generator results
    # ==============================

    gen_rows = []

    for gen in gens:
        p = get_result(gen, ["m:P:bus1", "m:Psum:bus1", "m:P"])
        q = get_result(gen, ["m:Q:bus1", "m:Qsum:bus1", "m:Q"])

        try:
            pgini = gen.pgini
        except Exception:
            pgini = ""

        try:
            qgini = gen.qgini
        except Exception:
            qgini = ""

        try:
            sgn = gen.sgn
        except Exception:
            sgn = ""

        qmin_attr, qmin_val = get_first_existing_attribute(
            gen,
            ["q_min", "qmin", "Qmin", "Q_min", "cQ_min", "cQmin", "qgmin", "qg_min"],
        )
        qmax_attr, qmax_val = get_first_existing_attribute(
            gen,
            ["q_max", "qmax", "Qmax", "Q_max", "cQ_max", "cQmax", "qgmax", "qg_max"],
        )
        control_attr, control_val = get_first_existing_attribute(
            gen,
            ["av_mode", "i_ctrl", "iopt_ctrl", "ctrl", "mode_inp", "iopt_pq", "iopt_mode"],
        )

        try:
            usetp = gen.usetp
        except Exception:
            usetp = ""

        try:
            desc = gen.desc
        except Exception:
            desc = ""

        try:
            bus1 = cubicle_to_terminal_name(gen.bus1)
        except Exception:
            bus1 = ""

        try:
            outserv = gen.outserv
        except Exception:
            outserv = ""

        gen_rows.append({
            "name": gen.loc_name,
            "bus": bus1,
            "pgini_mw": value_to_text(pgini),
            "qgini_mvar": value_to_text(qgini),
            "sgn_mva": value_to_text(sgn),
            "q_min_attr": qmin_attr,
            "q_min_mvar_pf": value_to_text(qmin_val),
            "q_max_attr": qmax_attr,
            "q_max_mvar_pf": value_to_text(qmax_val),
            "control_attr": control_attr,
            "control_value": value_to_text(control_val),
            "usetp_pu": value_to_text(usetp),
            "p_result_mw": value_to_text(p),
            "q_result_mvar": value_to_text(q),
            "outserv": value_to_text(outserv),
            "desc": desc,
        })

    write_csv(
        os.path.join(export_dir, "generator_results.csv"),
        [
            "name", "bus", "pgini_mw", "qgini_mvar", "sgn_mva",
            "q_min_attr", "q_min_mvar_pf", "q_max_attr", "q_max_mvar_pf",
            "control_attr", "control_value", "usetp_pu",
            "p_result_mw", "q_result_mvar", "outserv", "desc",
        ],
        gen_rows
    )

    log(app, "结果 CSV 已导出到:")
    log(app, export_dir)
    log(app, "导出文件:")
    log(app, "  bus_results.csv        buses: " + str(len(bus_rows)))
    log(app, "  line_results.csv       lines: " + str(len(line_rows)))
    log(app, "  germany_neighbor_line_capacity_detail.csv  lines: " + str(len(germany_neighbor_detail_rows)))
    log(app, "  germany_neighbor_line_capacity_summary.csv borders: " + str(len(germany_neighbor_summary_rows)))
    log(app, "  slack_results.csv      external grids: " + str(len(slack_rows)))
    log(app, "  load_results.csv       loads: " + str(len(load_rows)))
    log(app, "  generator_results.csv  generators: " + str(len(gen_rows)))


def print_basic_result_summary(app):
    """
    在 Output Window 里打印关键结果摘要。
    完整结果请看 CSV。
    """

    log_section(app, "步骤 14：关键结果摘要")

    lines = app.GetCalcRelevantObjects("*.ElmLne") or []
    xnets = app.GetCalcRelevantObjects("*.ElmXnet") or []

    log(app, "External Grid / Slack 结果:")

    for xnet in xnets:
        p = get_result(xnet, ["m:P:bus1", "m:Psum:bus1", "m:P"])
        q = get_result(xnet, ["m:Q:bus1", "m:Qsum:bus1", "m:Q"])

        log(
            app,
            "  "
            + xnet.loc_name
            + ": P = "
            + value_to_text(p)
            + " MW, Q = "
            + value_to_text(q)
            + " Mvar"
        )

    line_rows = []

    for line in lines:
        loading = get_result(line, ["c:loading", "m:loading"])

        try:
            p1 = float(get_result(line, ["m:P:bus1", "m:Psum:bus1"]))
            q1 = float(get_result(line, ["m:Q:bus1", "m:Qsum:bus1"]))
            p2 = float(get_result(line, ["m:P:bus2", "m:Psum:bus2"]))
            q2 = float(get_result(line, ["m:Q:bus2", "m:Qsum:bus2"]))
            s1 = math.sqrt(p1 ** 2 + q1 ** 2)
            s2 = math.sqrt(p2 ** 2 + q2 ** 2)
            rated_mva = math.sqrt(3.0) * float(line.typ_id.uline) * float(line.typ_id.sline)
            loading_num = max(s1, s2) / rated_mva * 100.0
        except Exception:
            try:
                loading_num = float(loading)
            except Exception:
                loading_num = -1.0

        line_rows.append((loading_num, line.loc_name))

    line_rows.sort(reverse=True, key=lambda x: x[0])

    log(app, "")
    log(app, "线路负载率 Top 20（按 P/Q 和额定电流重新计算）:")

    for loading, name in line_rows[:20]:
        if loading < 0:
            loading_txt = ""
        else:
            loading_txt = str(round(loading, 3))

        log(app, "  " + name + " : " + loading_txt + " %")

    print_german_interconnector_capacities(app, lines)


# ==============================
# 5. 主程序
# ==============================

try:
    app = powerfactory.GetApplication()

    if app is None:
        raise RuntimeError(
            "GetApplication() 返回 None。这个脚本必须在 PowerFactory 内部运行。"
            "请先用 D:\\PowerFactory.exe - Verknüpfung.lnk 打开 PF，"
            "再在 DIgSILENT-Bibliothek\\Skripte 中运行 loader。"
        )

    log_section(app, "步骤 1：PowerFactory 内部 Python 已连接")

    if not os.path.isdir(PF_IMPORT_DIR):
        raise FileNotFoundError("PF_IMPORT_DIR 不存在: " + PF_IMPORT_DIR)

    log(app, "PF_IMPORT_DIR = " + PF_IMPORT_DIR)
    log(app, "PF_IMPORT_DIR 文件:")
    for f in os.listdir(PF_IMPORT_DIR):
        log(app, "  - " + f)

    user = app.GetCurrentUser()
    log(app, "当前用户: " + user.loc_name)

    # ==============================
    # 激活项目
    # ==============================

    log_section(app, "步骤 2：激活项目")

    active_project = app.GetActiveProject()

    if active_project is None or active_project.loc_name != PROJECT_NAME:
        projects = user.GetContents("*.IntPrj")
        log(app, "项目数量: " + str(len(projects)))

        target_project = None
        for project in projects:
            log(app, "项目: " + project.loc_name)
            if project.loc_name == PROJECT_NAME:
                target_project = project

        if target_project is None:
            raise RuntimeError("没有找到项目: " + PROJECT_NAME)

        target_project.Activate()
        active_project = app.GetActiveProject()

    if active_project is None:
        raise RuntimeError("项目激活失败，当前没有 active project。")

    log(app, "已激活项目: " + active_project.loc_name)

    # ==============================
    # 激活 Study Case
    # ==============================

    log_section(app, "步骤 3：激活 Study Case")
    activate_or_create_study_case(app, STUDY_CASE_NAME)

    # ==============================
    # 创建 / 获取 Grid
    # ==============================

    log_section(app, "步骤 4：创建/删除 Grid")
    deactivate_other_grids(app, GRID_NAME)
    grid = get_or_create_grid(app)

    try:
        grid.Activate()
        log(app, "已激活 ElmNet: " + grid.loc_name)
    except Exception as e:
        log(app, "ElmNet Activate() 不可用或失败: " + repr(e))

    deactivate_other_grids(app, GRID_NAME)

    equip = get_project_folder_or_none(app, "equip")
    if equip is None:
        log(app, "没有找到 equip 类型库文件夹，线路类型将创建在 grid 里面。")
        type_folder = grid
    else:
        type_folder = equip

    terminals = {}
    connected_ac_buses = set()

    if SKIP_BUSES_WITHOUT_AC_LINES:
        connected_ac_buses = get_line_connected_bus_set()
        log(app, "出现在 pf_lines.csv 两端的 bus 数量: " + str(len(connected_ac_buses)))

    # ==============================
    # 导入 buses
    # ==============================

    if IMPORT_BUSES:
        log_section(app, "步骤 5：导入 buses")
        bus_path = os.path.join(PF_IMPORT_DIR, "pf_buses.csv")
        bus_rows = read_csv_dict(bus_path)
        log(app, "读取 pf_buses.csv: " + str(len(bus_rows)) + " 行")

        created_buses = 0
        updated_buses = 0
        skipped_non_ac_buses = 0
        skipped_isolated_buses = 0
        skipped_empty_buses = 0
        geo_written_buses = 0
        geo_failed_buses = 0

        for row in bus_rows:
            carrier = str(row.get("carrier", "")).strip()

            if ONLY_IMPORT_AC_BUSES and carrier and carrier != AC_CARRIER_NAME:
                skipped_non_ac_buses += 1
                continue

            name = safe_name(row.get("name", ""))
            voltage_kv = to_float(row.get("voltage_kv"), 380.0)

            if not name:
                skipped_empty_buses += 1
                continue

            if SKIP_BUSES_WITHOUT_AC_LINES and name not in connected_ac_buses:
                skipped_isolated_buses += 1
                log(app, "跳过无 AC line 连接的 bus: " + name)
                continue

            existing = grid.GetContents(name + ".ElmTerm")

            if existing:
                term = existing[0]
                updated_buses += 1
            else:
                term = grid.CreateObject("ElmTerm", name)
                created_buses += 1

            term.uknom = voltage_kv

            geo_ok = set_terminal_geo_coordinates(app, term, row)
            if geo_ok:
                geo_written_buses += 1
            else:
                geo_failed_buses += 1

            set_in_service(term)
            terminals[name] = term

        log(app, "ElmTerm 导入完成:")
        log(app, "  新建 buses: " + str(created_buses))
        log(app, "  更新 buses: " + str(updated_buses))
        log(app, "  跳过非 AC buses: " + str(skipped_non_ac_buses))
        log(app, "  跳过孤立 buses: " + str(skipped_isolated_buses))
        log(app, "  跳过空名称 buses: " + str(skipped_empty_buses))
        log(app, "  成功写入地理坐标 buses: " + str(geo_written_buses))
        log(app, "  未写入地理坐标 buses: " + str(geo_failed_buses))
        log(app, "  terminals 总数: " + str(len(terminals)))

    if not terminals:
        existing_terms = grid.GetContents("*.ElmTerm")
        for term in existing_terms:
            set_in_service(term)
            terminals[safe_name(term.loc_name)] = term
        log(app, "从已有 ElmTerm 读取 terminals: " + str(len(terminals)))

    # ==============================
    # 导入 lines
    # ==============================

    if IMPORT_LINES:
        log_section(app, "步骤 6：导入 lines")
        line_path = os.path.join(PF_IMPORT_DIR, "pf_lines.csv")
        line_rows = read_csv_dict(line_path)
        log(app, "读取 pf_lines.csv: " + str(len(line_rows)) + " 行")

        created_lines = 0
        updated_lines = 0
        skipped_lines = 0

        for i, row in enumerate(line_rows, start=1):
            name = safe_name(row.get("name", ""))
            from_bus = safe_name(row.get("from_bus", ""))
            to_bus = safe_name(row.get("to_bus", ""))

            if not name:
                skipped_lines += 1
                continue

            if from_bus not in terminals or to_bus not in terminals:
                log(app, "跳过线路，找不到 AC bus: " + name + "  " + from_bus + " -> " + to_bus)
                skipped_lines += 1
                continue

            voltage_kv = to_float(row.get("voltage_kv"), 380.0)
            length_km = to_float(row.get("length_km"), 1.0)
            r_ohm_per_km = to_float(row.get("r_ohm_per_km"), 0.03)
            x_ohm_per_km = to_float(row.get("x_ohm_per_km"), 0.30)
            rated_mva = to_float(row.get("rated_mva"), 1000.0)
            s_max_pu = to_float(row.get("s_max_pu"), 1.0)
            cline_uF_per_km = to_float(row.get("cline_uF_per_km"), 0.0)

            if length_km <= 0:
                length_km = 1.0

            existing = grid.GetContents(name + ".ElmLne")

            if existing:
                line = existing[0]
                updated_lines += 1
            else:
                line = grid.CreateObject("ElmLne", name)
                created_lines += 1

            type_name = row.get("type_name", "")
            if not type_name:
                type_name = "TypLne_" + name

            typ = get_or_create_line_type(
                app=app,
                type_folder=type_folder,
                type_name=type_name,
                voltage_kv=voltage_kv,
                r_ohm_per_km=r_ohm_per_km,
                x_ohm_per_km=x_ohm_per_km,
                rated_mva=rated_mva,
                cline_uF_per_km=cline_uF_per_km,
                s_max_pu=s_max_pu
            )

            cub1 = create_cubicle(terminals[from_bus], name + "_from")
            cub2 = create_cubicle(terminals[to_bus], name + "_to")

            line.bus1 = cub1
            line.bus2 = cub2
            line.typ_id = typ
            line.dline = length_km

            set_in_service(line)
            set_in_service(cub1)
            set_in_service(cub2)

            if i % 10 == 0:
                log(app, "  已导入线路 " + str(i) + "/" + str(len(line_rows)))

        log(app, "ElmLne 导入完成:")
        log(app, "  新建: " + str(created_lines))
        log(app, "  更新: " + str(updated_lines))
        log(app, "  跳过: " + str(skipped_lines))

    # ==============================
    # 导入 loads
    # ==============================

    hvdc_load_rows_for_qcap = []
    hvdc_gen_rows_for_qcap = []

    if IMPORT_LOADS:
        log_section(app, "步骤 7：导入 loads")
        load_path = os.path.join(PF_IMPORT_DIR, "pf_loads.csv")
        load_rows = read_csv_dict(load_path)
        log(app, "读取 pf_loads.csv: " + str(len(load_rows)) + " 行")
        import_load_rows_into_grid(app, grid, terminals, load_rows, "pf_loads.csv")

    if IMPORT_HVDC_EQUIVALENTS:
        log_section(app, "步骤 7b：导入 HVDC 等效 loads")
        hvdc_load_path = os.path.join(PF_IMPORT_DIR, HVDC_LOADS_FILE)
        hvdc_load_rows = read_optional_csv_dict(app, hvdc_load_path, HVDC_LOADS_FILE)
        hvdc_load_rows_for_qcap = hvdc_load_rows
        if hvdc_load_rows:
            import_load_rows_into_grid(app, grid, terminals, hvdc_load_rows, HVDC_LOADS_FILE)

    # ==============================
    # 导入 generators
    # ==============================

    if IMPORT_GENERATORS:
        log_section(app, "步骤 8：导入 generators")
        gen_path = os.path.join(PF_IMPORT_DIR, "pf_generators.csv")
        gen_rows = read_csv_dict(gen_path)
        log(app, "读取 pf_generators.csv: " + str(len(gen_rows)) + " 行")
        import_generator_rows_into_grid(app, grid, terminals, gen_rows, "pf_generators.csv")

        log(app, "  已尝试读取并写入 q_min_mvar / q_max_mvar / pf_control_mode。")
        log(app, "  如果 generator_results.csv 中 q_result_mvar 仍为 0，说明 ElmGenstat 的 PV 控制属性名在当前 PF 版本中未被这些候选名命中。")

    if IMPORT_HVDC_EQUIVALENTS:
        log_section(app, "步骤 8b：导入 HVDC 等效 generators")
        hvdc_gen_path = os.path.join(PF_IMPORT_DIR, HVDC_GENERATORS_FILE)
        hvdc_gen_rows = read_optional_csv_dict(app, hvdc_gen_path, HVDC_GENERATORS_FILE)
        hvdc_gen_rows_for_qcap = hvdc_gen_rows
        if hvdc_gen_rows:
            import_generator_rows_into_grid(app, grid, terminals, hvdc_gen_rows, HVDC_GENERATORS_FILE)

        create_hvdc_q_support_devices_by_bus(
            app,
            grid,
            terminals,
            hvdc_gen_rows_for_qcap,
            hvdc_load_rows_for_qcap,
        )

        log_hvdc_summary(app)

    # ==============================
    # 导入 external grid
    # ==============================

    if IMPORT_EXTERNAL_GRID:
        log_section(app, "步骤 9：导入 external grid")
        xnet_path = os.path.join(PF_IMPORT_DIR, "pf_external_grid.csv")
        xnet_rows = read_csv_dict(xnet_path)
        log(app, "读取 pf_external_grid.csv: " + str(len(xnet_rows)) + " 行")

        created_xnets = 0
        updated_xnets = 0
        skipped_xnets = 0

        for row in xnet_rows:
            name = safe_name(row.get("name", ""))
            bus = safe_name(row.get("bus", ""))

            if not name:
                skipped_xnets += 1
                continue

            if bus not in terminals:
                log(app, "跳过外部电网，找不到 AC bus: " + name + "  bus=" + bus)
                skipped_xnets += 1
                continue

            existing = grid.GetContents(name + ".ElmXnet")

            if existing:
                xnet = existing[0]
                updated_xnets += 1
            else:
                xnet = grid.CreateObject("ElmXnet", name)
                created_xnets += 1

            cub = create_cubicle(terminals[bus], name)
            xnet.bus1 = cub

            try:
                xnet.usetp = to_float(row.get("voltage_setpoint_pu", row.get("voltage_setpoint", 1.0)), 1.0)
            except Exception:
                pass

            configure_external_grid_settings(
                app,
                xnet,
                to_float(row.get("voltage_setpoint_pu", row.get("voltage_setpoint", 1.0)), 1.0),
            )

            set_in_service(xnet)
            set_in_service(cub)

        log(app, "ElmXnet 导入完成:")
        log(app, "  新建: " + str(created_xnets))
        log(app, "  更新: " + str(updated_xnets))
        log(app, "  跳过: " + str(skipped_xnets))

    ensure_required_external_grids(app, grid, terminals)

    # ==============================
    # 确保至少有 external grid
    # ==============================

    grid_xnets = grid.GetContents("*.ElmXnet")
    log(app, "")
    log(app, "Grid 内 ElmXnet 数量: " + str(len(grid_xnets)))
    for x in grid_xnets:
        log(app, "  Grid ElmXnet: " + x.loc_name)

    if not grid_xnets:
        ensure_external_grid(app, grid, terminals, slack_bus_name=DEFAULT_SLACK_BUS)

    log_section(app, "步骤 9b：创建 Station Controller 并分配同 bus 发电机 Q 控制")
    create_station_controllers_by_bus(app, grid, terminals)

    try:
        grid.Activate()
        log(app, "再次激活 ElmNet: " + grid.loc_name)
    except Exception as e:
        log(app, "再次激活 ElmNet 失败: " + repr(e))

    # ==============================
    # 检查导入结果
    # ==============================

    log_section(app, "步骤 10：检查导入结果")

    terms = app.GetCalcRelevantObjects("*.ElmTerm")
    lines = app.GetCalcRelevantObjects("*.ElmLne")
    loads = app.GetCalcRelevantObjects("*.ElmLod")
    gens = app.GetCalcRelevantObjects("*.ElmGenstat")
    xnets = app.GetCalcRelevantObjects("*.ElmXnet")

    log(app, "当前项目可计算对象数量:")
    log(app, "  ElmTerm: " + str(len(terms) if terms else 0))
    log(app, "  ElmLne: " + str(len(lines) if lines else 0))
    log(app, "  ElmLod: " + str(len(loads) if loads else 0))
    log(app, "  ElmGenstat: " + str(len(gens) if gens else 0))
    log(app, "  ElmXnet: " + str(len(xnets) if xnets else 0))

    print_power_balance(app, loads, gens)
    inspect_xnets(app, grid)

    if not xnets:
        log(app, "警告：GetCalcRelevantObjects 没有找到 ElmXnet。可能是当前 Study Case / 网络激活范围问题。")

    # ==============================
    # 保存项目
    # ==============================

    log_section(app, "步骤 11：保存项目")
    try:
        app.WriteChangesToDb()
        log(app, "项目修改已写入数据库。")
    except Exception as e:
        log(app, "WriteChangesToDb 保存时出现问题: " + repr(e))

    # ==============================
    # 运行 Load Flow
    # ==============================

    log_section(app, "步骤 12：运行 Load Flow")

    dc_result = None
    ac_result = None

    if RUN_DC_LOAD_FLOW:
        dc_result = run_dc_load_flow(app)

    if RUN_AC_LOAD_FLOW:
        ac_result = run_ac_load_flow(app)

    if EXPORT_RESULTS_TO_CSV:
        if ac_result == 0 or dc_result == 0:
            export_load_flow_results_to_csv(app, RESULT_EXPORT_DIR)
            print_basic_result_summary(app)
        else:
            log(app, "Load Flow 没有成功，未导出结果 CSV。")
            log(app, "dc_result = " + str(dc_result))
            log(app, "ac_result = " + str(ac_result))

    log_section(app, "脚本完成")
    log(app, "PowerFactory CSV 导入、潮流计算与结果导出完成。")
    log(app, "CSV 结果文件夹: " + RESULT_EXPORT_DIR)
    log(app, "请查看当前 PowerFactory GUI 的 Output Window / Ausgabefenster。")
    log(app, "因为脚本在 PowerFactory 内部运行，GUI 会保持打开。")

except Exception as error:
    try:
        app_for_log = powerfactory.GetApplication()
        if app_for_log is not None:
            log_section(app_for_log, "脚本发生错误")
            log(app_for_log, repr(error))
            log(app_for_log, traceback.format_exc())
        else:
            print("脚本发生错误:")
            print(repr(error))
            print(traceback.format_exc())
    except Exception:
        print("脚本发生错误:")
        print(repr(error))
        print(traceback.format_exc())
