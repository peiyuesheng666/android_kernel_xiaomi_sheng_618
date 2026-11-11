
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
typedef uint32_t u32;
#define HZ 1000UL
#define time_before(a,b) ((long)((a)-(b))<0)
#define READ_ONCE(x) (x)
#define module_param_named(a,b,c,d)
#define MODULE_PARM_DESC(a,b)
#define PMIC_GLINK_STATE_UP 1
#define POWER_SUPPLY_USB_TYPE_PD_PPS 9
#define POWER_SUPPLY_HEALTH_GOOD 1
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct work_struct {int dummy;};
struct delayed_work {struct work_struct work;};
struct class {int dummy;};
struct class_attribute {int dummy;};
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
#define system_freezable_wq ((void *)1)
#define dev_info(dev,fmt,...) ((void)(dev))
#define dev_warn(dev,fmt,...) ((void)(dev))
static int atomic_read(int *p){return *p;}
static void atomic_inc(int *p){++*p;}
static int atomic_xchg(int *p,int v){int old=*p;*p=v;return old;}
static void mutex_lock(int *p){assert(*p==0);*p=1;}
static void mutex_unlock(int *p){assert(*p==1);*p=0;}
static int scheduled,notifications;
static unsigned long last_delay;
static int mod_delayed_work(void *q,struct delayed_work *w,unsigned long delay){
    (void)q;(void)w;++scheduled;last_delay=delay;return 1;
}
#define queue_delayed_work mod_delayed_work
static void schedule_delayed_work(struct delayed_work *w,unsigned long delay){(void)w;(void)delay;++notifications;}
static void power_supply_changed(void *p){assert(p);++notifications;}
static int kstrtobool(const char *s,bool *v){
    if(!strcmp(s,"1")){*v=true;return 0;}if(!strcmp(s,"0")){*v=false;return 0;}return -EINVAL;
}
enum psy_type {
	PSY_TYPE_BATTERY,
	PSY_TYPE_USB,
	PSY_TYPE_WLS,
	PSY_TYPE_XM,
	PSY_TYPE_MAX,
};
enum battery_property_id {
	BATT_STATUS,
	BATT_HEALTH,
	BATT_PRESENT,
	BATT_CHG_TYPE,
	BATT_CAPACITY,
	BATT_SOH,
	BATT_VOLT_OCV,
	BATT_VOLT_NOW,
	BATT_VOLT_MAX,
	BATT_CURR_NOW,
	BATT_CHG_CTRL_LIM,
	BATT_CHG_CTRL_LIM_MAX,
	BATT_CONSTANT_CURRENT,
	BATT_TEMP,
	BATT_TECHNOLOGY,
	BATT_CHG_COUNTER,
	BATT_CYCLE_COUNT,
	BATT_CHG_FULL_DESIGN,
	BATT_CHG_FULL,
	BATT_MODEL_NAME,
	BATT_TTF_AVG,
	BATT_TTE_AVG,
	BATT_RESISTANCE,
	BATT_POWER_NOW,
	BATT_POWER_AVG,
	BATT_PROP_MAX,
};
enum usb_property_id {
	USB_ONLINE,
	USB_VOLT_NOW,
	USB_VOLT_MAX,
	USB_CURR_NOW,
	USB_CURR_MAX,
	USB_INPUT_CURR_LIMIT,
	USB_TYPE,
	USB_ADAP_TYPE,
	USB_MOISTURE_DET_EN,
	USB_MOISTURE_DET_STS,
	USB_TEMP,
	USB_REAL_TYPE,
	USB_TYPEC_COMPLIANT,
	USB_PROP_MAX,
};
enum xm_property_id {
	XM_PROP_RESISTANCE_ID = 0,	/* v */
	XM_PROP_VERIFY_DIGEST = 1,	/* v */
	XM_PROP_CONNECTOR_TEMP = 2,	/* v */
	XM_PROP_AUTHENTIC = 3,	/* v */
	XM_PROP_BATTERY_ADAPT_POWER_MATCH = 4,	/* v */
	XM_PROP_CHIP_OK = 5,	/* v */
	XM_PROP_VBUS_DISABLE = 6,	/* p */
	XM_PROP_REAL_TYPE = 7,	/* v */
	XM_PROP_THERMAL_BOARD_TEMP = 8,	/* v */
	XM_PROP_NTC_ALARM = 9,	/* v */
	XM_PROP_CHARGER_USER_VALUE_MAP = 10,	/* v */
	XM_PROP_CLOUD_CONTROL_CID_MODE = 11,	/* v */
	XM_PROP_VERIFY_PROCESS = 12,	/* v */
	XM_PROP_VDM_CMD_CHARGER_VERSION = 13,	/* v */
	XM_PROP_VDM_CMD_CHARGER_VOLTAGE = 14,	/* v */
	XM_PROP_VDM_CMD_CHARGER_TEMP = 15,	/* v */
	XM_PROP_VDM_CMD_SESSION_SEED = 16,	/* v */
	XM_PROP_VDM_CMD_AUTHENTICATION = 17,	/* v */
	XM_PROP_VDM_CMD_VERIFIED = 18,	/* v */
	XM_PROP_VDM_CMD_REMOVE_COMPENSATION = 19,	/* v */
	XM_PROP_VDM_CMD_REVERSE_AUTHEN = 20,	/* v */
	XM_PROP_CURRENT_STATE = 21,	/* v */
	XM_PROP_ADAPTER_ID = 22,	/* v */
	XM_PROP_ADAPTER_SVID = 23,	/* v */
	XM_PROP_PD_VERIFED = 24,	/* v */
	XM_PROP_PDO2 = 25,	/* v */
	XM_PROP_UVDM_STATE = 26,	/* v */
	XM_PROP_BQ2597X_CHIP_OK = 27,	/* v */
	XM_PROP_BQ2597X_SLAVE_CHIP_OK = 28,	/* v */
	XM_PROP_BQ2597X_BUS_CURRENT = 29,	/* v */
	XM_PROP_BQ2597X_SLAVE_BUS_CURRENT = 30,	/* v */
	XM_PROP_BQ2597X_BUS_DELTA = 31,	/* v */
	XM_PROP_BQ2597X_BUS_VOLTAGE = 32,	/* v */
	XM_PROP_BQ2597X_BATTERY_PRESENT = 33,	/* v */
	XM_PROP_BQ2597X_SLAVE_BATTERY_PRESENT = 34,	/* v */
	XM_PROP_BQ2597X_BATTERY_VOLTAGE = 35,	/* v */
	XM_PROP_MASTER_SMB1396_ONLINE = 36,	/* p */
	XM_PROP_MASTER_SMB1396_IIN = 37,	/* p */
	XM_PROP_SLAVE_SMB1396_ONLINE = 38,	/* p */
	XM_PROP_SLAVE_SMB1396_IIN = 39,	/* p */
	XM_PROP_SMB_IIN_DIFF = 40,	/* p */
	XM_PROP_CC_ORIENTATION = 41,	/* v */
	XM_PROP_INPUT_SUSPEND = 42,	/* v */
	XM_PROP_FASTCHGMODE = 43,	/* v */
	XM_PROP_NIGHT_CHARGING = 44,	/* v */
	XM_PROP_BLANK_STATUS = 45,	/* v */
	XM_PROP_SCREEN_CCTOG = 46,	/* v */
	XM_PROP_SOC_DECIMAL = 47,	/* v */
	XM_PROP_SOC_DECIMAL_RATE = 48,	/* v */
	XM_PROP_QUICK_CHARGE_TYPE = 49,	/* p */
	XM_PROP_APDO_MAX = 50,	/* v */
	XM_PROP_POWER_MAX = 51,	/* v */
	XM_PROP_DIE_TEMPERATURE = 52,	/* p */
	XM_PROP_SLAVE_DIE_TEMPERATURE = 53,	/* p */
	XM_PROP_FG_RAW_SOC = 54,	/* v */
	XM_PROP_WLS_START = 55,	/* p */
	XM_PROP_TX_MACL = 56,	/* v */
	XM_PROP_TX_MACH = 57,	/* v */
	XM_PROP_RX_CRL = 58,	/* v */
	XM_PROP_RX_CRH = 59,	/* v */
	XM_PROP_RX_CEP = 60,	/* v */
	XM_PROP_BT_STATE = 61,	/* v */
	XM_PROP_REVERSE_CHG_MODE = 62,	/* v */
	XM_PROP_REVERSE_CHG_STATE = 63,	/* v */
	XM_PROP_RX_VOUT = 64,	/* v */
	XM_PROP_RX_VRECT = 65,	/* v */
	XM_PROP_RX_IOUT = 66,	/* v */
	XM_PROP_TX_ADAPTER = 67,	/* v */
	XM_PROP_OP_MODE = 68,	/* v */
	XM_PROP_WLS_DIE_TEMP = 69,	/* v */
	XM_PROP_WLS_BIN = 70,	/* v */
	XM_PROP_WLSCHARGE_CONTROL_LIMIT = 71,	/* v */
	XM_PROP_FW_VER = 72,	/* v */
	XM_PROP_WIRELESS_TX_UUID = 73,	/* v */
	XM_PROP_WLS_THERMAL_REMOVE = 74,	/* v */
	XM_PROP_CHG_DEBUG = 75,	/* v */
	XM_PROP_WLS_FW_STATE = 76,	/* v */
	XM_PROP_WLS_CAR_ADAPTER = 77,	/* v */
	XM_PROP_WLS_TX_SPEED = 78,	/* v */
	XM_PROP_WLS_FC_FLAG = 79,	/* v */
	XM_PROP_RX_SS = 80,	/* v */
	XM_PROP_RX_OFFSET = 81,	/* v */
	XM_PROP_TX_Q = 82,	/* v */
	XM_PROP_PEN_MACL = 83,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_MACH = 84,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_TX_IOUT = 85,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_TX_VOUT = 86,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_SOC = 87,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_HALL3 = 88,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_HALL4 = 89,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_TX_SS = 90,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_PEN_PLACE_ERR = 91,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_FAKE_SS = 92,	/* MiCode wireless block + shipped sheng offset */
	XM_PROP_SHUTDOWN_DELAY = 94,	/* v */
	XM_PROP_FAKE_TEMP = 95,	/* v */
	XM_PROP_THERMAL_REMOVE = 96,	/* v */
	XM_PROP_TYPEC_MODE = 97,	/* v */
	XM_PROP_MTBF_CURRENT = 98,	/* v */
	XM_PROP_THERMAL_TEMP = 99,	/* v */
	XM_PROP_FB_BLANK_STATE = 100,	/* p */
	XM_PROP_SMART_BATT = 101,	/* v */
	XM_PROP_SHIPMODE_COUNT_RESET = 102,	/* v */
	XM_PROP_SPORT_MODE = 103,	/* p */
	XM_PROP_BATT_CONNT_ONLINE = 104,	/* v */
	XM_PROP_FAKE_CYCLE = 105,	/* v */
	XM_PROP_AFP_TEMP = 106,	/* v */
	XM_PROP_PLATE_SHOCK = 107,	/* v */
	XM_PROP_CC_SHORT_VBUS = 108,	/* v */
	XM_PROP_OTG_UI_SUPPORT = 109,	/* v */
	XM_PROP_CID_STATUS = 110,	/* v */
	XM_PROP_CC_TOGGLE = 111,	/* v */
	XM_PROP_SMART_CHG = 112,	/* v */
	XM_PROP_BATTERY_PARAM_RESET = 113,	/* v */
	XM_PROP_NVTFG_MONITOR_ISC = 114,	/* v */
	XM_PROP_NVTFG_MONITOR_SOA = 115,	/* v */
	XM_PROP_OVER_PEAK_FLAG = 116,	/* p */
	XM_PROP_CURRENT_DEVIATION = 117,	/* p */
	XM_PROP_POWER_DEVIATION = 118,	/* p */
	XM_PROP_AVERAGE_CURRENT = 119,	/* p */
	XM_PROP_AVERAGE_TEMPERATURE = 120,	/* p */
	XM_PROP_START_LEARNING = 121,	/* p */
	XM_PROP_STOP_LEARNING = 122,	/* p */
	XM_PROP_SET_LEARNING_POWER = 123,	/* p */
	XM_PROP_GET_LEARNING_POWER = 124,	/* p */
	XM_PROP_GET_LEARNING_POWER_DEV = 125,	/* p */
	XM_PROP_GET_LEARNING_TIME_DEV = 126,	/* p */
	XM_PROP_SET_CONSTANT_POWER = 127,	/* p */
	XM_PROP_GET_REMAINING_TIME = 128,	/* p */
	XM_PROP_SET_REFERANCE_POWER = 129,	/* p */
	XM_PROP_GET_REFERANCE_CURRENT = 130,	/* p */
	XM_PROP_GET_REFERANCE_POWER = 131,	/* p */
	XM_PROP_START_LEARNING_B = 132,	/* p */
	XM_PROP_STOP_LEARNING_B = 133,	/* p */
	XM_PROP_SET_LEARNING_POWER_B = 134,	/* p */
	XM_PROP_GET_LEARNING_POWER_B = 135,	/* p */
	XM_PROP_GET_LEARNING_POWER_DEV_B = 136,	/* p */
	XM_PROP_FG1_QMAX = 137,	/* v */
	XM_PROP_FG1_RM = 138,	/* v */
	XM_PROP_FG1_FCC = 139,	/* v */
	XM_PROP_FG1_SOH = 140,	/* v */
	XM_PROP_FG1_FCC_SOH = 141,	/* v */
	XM_PROP_FG1_CYCLE = 142,	/* v */
	XM_PROP_FG1_FAST_CHARGE = 143,	/* v */
	XM_PROP_FG1_CURRENT_MAX = 144,	/* v */
	XM_PROP_FG1_VOL_MAX = 145,	/* v */
	XM_PROP_FG1_TSIM = 146,	/* v */
	XM_PROP_FG1_TAMBIENT = 147,	/* v */
	XM_PROP_FG1_TREMQ = 148,	/* v */
	XM_PROP_FG1_TFULLQ = 149,	/* v */
	XM_PROP_FG1_RSOC = 150,	/* v */
	XM_PROP_FG1_AI = 151,	/* v */
	XM_PROP_FG1_CELL1_VOL = 152,	/* p */
	XM_PROP_FG1_CELL2_VOL = 153,	/* p */
	XM_PROP_FG1_TEMP_MAX = 154,	/* v */
	XM_PROP_FG1_TIME_HT = 155,	/* v */
	XM_PROP_FG1_TIME_OT = 156,	/* v */
	XM_PROP_FG1_SEAL_SET = 157,	/* v */
	XM_PROP_FG1_SEAL_STATE = 158,	/* v */
	XM_PROP_FG1_DF_CHECK = 159,	/* v */
	XM_PROP_BATT_SN = 160,	/* v */
	XM_PROP_MAX_LIFE_VOL = 161,	/* v */
	XM_PROP_MAX_LIFE_TEMP = 162,	/* v */
	XM_PROP_OVER_VOL_DURATION = 163,	/* v */
	XM_PROP_BATT_EMERG = 164,	/* v */
	XM_PROP_SLAVE_AUTHENTIC = 165,	/* sheng shipping slave_authentic */
	XM_PROP_FG_VENDOR_ID = 216,	/* v */
	XM_PROP_DAM_OVPGATE = 218,	/* v */
	XM_PROP_CHARGING_SUSPEND_BATTERY = 219,	/* v */
	XM_PROP_IS_EU_MODEL = 230,	/* v */
	XM_PROP_PPS_PTF = 231,	/* v */
	XM_PROP_DOD_COUNT = 223,	/* v */
	XM_PROP_BATT_CAPACITY_INCREASE = 224,	/* v */
	XM_PROP_BATT_SPEC = 225,	/* v */
	XM_PROP_BATT_SPEC_ENABLE = 226,	/* v */
	XM_PROP_BATT_DEVICE_NAME = 227,	/* v */
	XM_PROP_PACK_VENDOR = 228,	/* v */
	XM_PROP_LAST_NODE = 232,	/* v */
	XM_PROP_MAX = 233,
};/* SPDX-License-Identifier: GPL-2.0-only */
/* Shared production policy; native adapter authentication always has priority. */
struct sheng_pps_sample {
    bool online, pps, ready, verified, healthy, authenticated, input_suspended, verifying;
    u32 svid, adapter_id, apdo_watts, power_watts;
};
struct sheng_pps_policy {
    bool connected;
    unsigned int attempts;
};
enum sheng_pps_action {
    SHENG_PPS_OFFLINE, SHENG_PPS_EXISTING, SHENG_PPS_NATIVE,
    SHENG_PPS_BLOCKED, SHENG_PPS_UNLOCK
};

static enum sheng_pps_action sheng_pps_decide(struct sheng_pps_policy *p,
        const struct sheng_pps_sample *s)
{
    if (!s->online) {
        memset(p, 0, sizeof(*p));
        return SHENG_PPS_OFFLINE;
    }
    p->connected = true;
    if (s->verified)
        return SHENG_PPS_EXISTING;
    /* SVID can be retained after unplug. A zero native adapter ID plus current
     * <100 W capability is eligible even when an old Xiaomi SVID remains. */
    if (!s->pps || s->adapter_id || ((!s->svid || s->svid == 0x2717) &&
            (s->apdo_watts >= 100 || s->power_watts >= 100))) {
        return SHENG_PPS_NATIVE;
    }
    if (s->verifying || !s->ready || !s->apdo_watts || !s->power_watts) {
        return SHENG_PPS_BLOCKED;
    }
    if (p->attempts >= 3 || !s->healthy ||
            !s->authenticated || s->input_suspended) {
        return SHENG_PPS_BLOCKED;
    }
    return SHENG_PPS_UNLOCK;
}

struct psy_state {u32 prop[233];void *psy;};
struct battery_chg_dev {
    int state,sheng_pps_epoch,sheng_pps_reset,sheng_pps_lock;
    bool sheng_pps_stopping,debug_battery_detected,block_tx;
    struct class battery_class;
    struct delayed_work sheng_pps_work,xm_prop_change_work;
    struct sheng_pps_policy sheng_pps;
    struct psy_state psy_list[PSY_TYPE_MAX];
    void *dev;
};
static int reads,writes,remote_rc,write_rc,ack_one=1;
static int drop_at,notify_at,native_at,disable_at,unplug_on_write;
static bool sheng_pps_auto_verify;
static int read_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id){
    assert(b->sheng_pps_lock==1 && id<233);(void)p;++reads;
    if(reads==drop_at)b->state=0;
    if(reads==notify_at)++b->sheng_pps_epoch;
    if(reads==native_at)b->psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=2;
    if(reads==disable_at)sheng_pps_auto_verify=false;
    return remote_rc;
}
static int write_property_id(struct battery_chg_dev *b,struct psy_state *p,u32 id,u32 v){
    assert(b->sheng_pps_lock==1 && p==&b->psy_list[PSY_TYPE_XM] && (id==XM_PROP_PD_VERIFED || id==XM_PROP_VERIFY_PROCESS) && v<=1);
    ++writes;if(write_rc)return write_rc;
    if(ack_one)p->prop[id]=v;
    if(unplug_on_write)b->psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=0;
    return 0;
}
/* SPDX-License-Identifier: GPL-2.0-only */
/* Declaration supplied before transport shims; reset() sets the production default. */
module_param_named(sheng_pps_auto_verify, sheng_pps_auto_verify, bool, 0600);
MODULE_PARM_DESC(sheng_pps_auto_verify,
        "Maintain eligible third-party PPS after native discovery; N disables automatic writes");

static bool sheng_pps_live(struct battery_chg_dev *bcdev)
{
    return !READ_ONCE(bcdev->sheng_pps_stopping) &&
        atomic_read(&bcdev->state) == PMIC_GLINK_STATE_UP &&
        !(bcdev->debug_battery_detected && bcdev->block_tx);
}

static int sheng_pps_read(struct battery_chg_dev *bcdev, int type, u32 id, u32 *value)
{
    struct psy_state *pst = &bcdev->psy_list[type];
    int rc;
    if (!sheng_pps_live(bcdev))
        return -ENOTCONN;
    rc = read_property_id(bcdev, pst, id);
    if (rc < 0)
        return rc;
    if (!sheng_pps_live(bcdev))
        return -ENOTCONN;
    *value = READ_ONCE(pst->prop[id]);
    return 0;
}

static int sheng_pps_snapshot(struct battery_chg_dev *bcdev, struct sheng_pps_sample *s)
{
    u32 value, main_auth, slave_auth, match;
    int rc;
    memset(s, 0, sizeof(*s));
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_ONLINE, &value);
    if (rc < 0)
        return rc;
    s->online = value == 1;
    if (!s->online)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_REAL_TYPE, &value);
    if (rc < 0)
        return rc;
    s->pps = value == POWER_SUPPLY_USB_TYPE_PD_PPS;
    if (!s->pps)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_PD_VERIFED, &value);
    if (rc < 0)
        return rc;
    s->verified = value == 1;
    if (s->verified)
        return 0;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_CURRENT_STATE, &value);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_VERIFY_PROCESS, &match);
    if (rc < 0)
        return rc;
    s->verifying = match != 0;
    /* Shipping current_state_show maps firmware state 31 to SNK_Ready. */
    s->ready = value == 31;
#define SHENG_PPS_GET(id, field) do { \
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, id, &s->field); \
    if (rc < 0) return rc; \
} while (0)
    SHENG_PPS_GET(XM_PROP_ADAPTER_SVID, svid);
    SHENG_PPS_GET(XM_PROP_ADAPTER_ID, adapter_id);
    SHENG_PPS_GET(XM_PROP_APDO_MAX, apdo_watts);
    SHENG_PPS_GET(XM_PROP_POWER_MAX, power_watts);
#undef SHENG_PPS_GET
    rc = sheng_pps_read(bcdev, PSY_TYPE_BATTERY, BATT_HEALTH, &value);
    if (rc < 0)
        return rc;
    s->healthy = value == POWER_SUPPLY_HEALTH_GOOD;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_AUTHENTIC, &main_auth);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_SLAVE_AUTHENTIC, &slave_auth);
    if (rc < 0)
        return rc;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_BATTERY_ADAPT_POWER_MATCH, &match);
    if (rc < 0)
        return rc;
    s->authenticated = main_auth == 1 && slave_auth == 1 && match == 1;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_INPUT_SUSPEND, &value);
    if (rc < 0)
        return rc;
    s->input_suspended = value != 0;
    return 0;
}

static void sheng_pps_auto_work(struct work_struct *work)
{
    struct battery_chg_dev *bcdev = container_of(to_delayed_work(work),
            struct battery_chg_dev, sheng_pps_work);
    struct sheng_pps_sample sample, first;
    enum sheng_pps_action action;
    int epoch;
    u32 verified, online, type;
    bool retry = false, changed = false;
    unsigned long retry_delay = 0;
    int rc;
    if (!READ_ONCE(sheng_pps_auto_verify) || READ_ONCE(bcdev->sheng_pps_stopping))
        return;
    mutex_lock(&bcdev->sheng_pps_lock);
    if (atomic_xchg(&bcdev->sheng_pps_reset, 0))
        memset(&bcdev->sheng_pps, 0, sizeof(bcdev->sheng_pps));
    epoch = atomic_read(&bcdev->sheng_pps_epoch);
    rc = sheng_pps_snapshot(bcdev, &sample);
    if (rc < 0)
        goto error;
    action = sheng_pps_decide(&bcdev->sheng_pps, &sample);
    /* Only attached PPS is monitored; already verified samples cost three reads.
     * Events and stores kick immediately. The five-second fallback catches
     * firmware-only clears; it is not a recognition grace period. */
    retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;
    retry_delay = 5 * HZ;
    if (action != SHENG_PPS_UNLOCK)
        goto out;
    /* Revalidate the complete source and protection state immediately before writing. */
    first = sample;
    rc = sheng_pps_snapshot(bcdev, &sample);
    if (rc < 0)
        goto error;
    action = sheng_pps_decide(&bcdev->sheng_pps, &sample);
    if (action != SHENG_PPS_UNLOCK || !READ_ONCE(sheng_pps_auto_verify) ||
            !sheng_pps_live(bcdev) || epoch != atomic_read(&bcdev->sheng_pps_epoch)) {
        retry = sample.online && sample.pps && bcdev->sheng_pps.attempts < 3;
        retry_delay = 0;
        goto out;
    }
    if (first.svid != sample.svid || first.adapter_id != sample.adapter_id ||
            first.apdo_watts != sample.apdo_watts || first.power_watts != sample.power_watts) {
        retry = true;
        retry_delay = 0;
        goto out;
    }
    rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], XM_PROP_PD_VERIFED, 1);
    if (rc < 0)
        goto write_error;
    rc = sheng_pps_read(bcdev, PSY_TYPE_XM, XM_PROP_PD_VERIFED, &verified);
    if (rc < 0)
        goto write_error;
    if (verified != 1) {
        rc = -EIO;
        goto write_error;
    }
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_ONLINE, &online);
    if (rc < 0)
        goto write_error;
    rc = sheng_pps_read(bcdev, PSY_TYPE_USB, USB_REAL_TYPE, &type);
    if (rc < 0)
        goto write_error;
    if (online != 1 || type != POWER_SUPPLY_USB_TYPE_PD_PPS) {
        rc = -ENOTCONN;
        goto write_error;
    }
    dev_info(bcdev->dev, "sheng PPS auto verified: svid=%04x id=%08x APDO=%u W\n",
            sample.svid, sample.adapter_id, sample.apdo_watts);
    bcdev->sheng_pps.attempts = 0;
    changed = true;
    goto out;
error:
write_error:
    if (bcdev->sheng_pps.attempts < 3)
        ++bcdev->sheng_pps.attempts;
    retry_delay = HZ;
    retry = bcdev->sheng_pps.attempts < 3 && sheng_pps_live(bcdev);
    dev_warn(bcdev->dev, "sheng PPS auto verification deferred/failed: %d\n", rc);
out:
    mutex_unlock(&bcdev->sheng_pps_lock);
    if (changed && !READ_ONCE(bcdev->sheng_pps_stopping)) {
        if (bcdev->psy_list[PSY_TYPE_USB].psy)
            power_supply_changed(bcdev->psy_list[PSY_TYPE_USB].psy);
        schedule_delayed_work(&bcdev->xm_prop_change_work, 0);
    }
    if (retry && READ_ONCE(sheng_pps_auto_verify) && !READ_ONCE(bcdev->sheng_pps_stopping))
        mod_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, retry_delay);
}

static void sheng_pps_kick(struct battery_chg_dev *bcdev)
{
    if (READ_ONCE(sheng_pps_auto_verify) && !READ_ONCE(bcdev->sheng_pps_stopping))
        mod_delayed_work(system_freezable_wq, &bcdev->sheng_pps_work, 0);
}
static ssize_t pd_verifed_store(const struct class *c,
        const struct class_attribute *attr, const char *buf, size_t count)
{
    struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev, battery_class);
    bool val;
    int rc;
    if (kstrtobool(buf, &val))
        return -EINVAL;
    mutex_lock(&bcdev->sheng_pps_lock);
    rc = sheng_pps_live(bcdev) ?
        write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM], XM_PROP_PD_VERIFED, val) :
        -ENOTCONN;
    if (rc >= 0 && !sheng_pps_live(bcdev))
        rc = -ENOTCONN;
    /* batterysecret also writes zero on third-party auth failure. Automatic
     * mode re-evaluates the live source instead of inhibiting the connection. */
    mutex_unlock(&bcdev->sheng_pps_lock);
    if (rc < 0)
        return rc;
    sheng_pps_kick(bcdev);
    return count;
}static ssize_t verify_process_store(const struct class *c,
					const struct class_attribute *attr,
					const char *buf, size_t count)
{
	struct battery_chg_dev *bcdev = container_of(c, struct battery_chg_dev,
						battery_class);
	int rc;
	bool val;

	if (kstrtobool(buf, &val))
		return -EINVAL;

	mutex_lock(&bcdev->sheng_pps_lock);
	atomic_inc(&bcdev->sheng_pps_epoch);
	rc = write_property_id(bcdev, &bcdev->psy_list[PSY_TYPE_XM],
				XM_PROP_VERIFY_PROCESS, val);
	mutex_unlock(&bcdev->sheng_pps_lock);
	if (rc < 0)
		return rc;

	sheng_pps_kick(bcdev);
	return count;
}
static void reset(struct battery_chg_dev *b){
    memset(b,0,sizeof(*b));b->state=1;b->dev=b;
    b->psy_list[PSY_TYPE_USB].psy=b;
    b->psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=1;
    b->psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=POWER_SUPPLY_USB_TYPE_PD_PPS;
    b->psy_list[PSY_TYPE_BATTERY].prop[BATT_HEALTH]=POWER_SUPPLY_HEALTH_GOOD;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_AUTHENTIC]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_SLAVE_AUTHENTIC]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_BATTERY_ADAPT_POWER_MATCH]=1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x12d1;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=90;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_POWER_MAX]=90;
    b->psy_list[PSY_TYPE_XM].prop[XM_PROP_CURRENT_STATE]=31;
    reads=writes=scheduled=notifications=remote_rc=write_rc=0;ack_one=1;
    drop_at=notify_at=native_at=disable_at=unplug_on_write=0;
    sheng_pps_auto_verify=true;
}
static void run(struct battery_chg_dev *b){sheng_pps_auto_work(&b->sheng_pps_work.work);assert(b->sheng_pps_lock==0);}
static void prime(struct battery_chg_dev *b){reset(b);}
int main(void){
    struct battery_chg_dev b;struct sheng_pps_policy p={0};
    struct sheng_pps_sample s={.online=true,.pps=true,.ready=true,.healthy=true,.authenticated=true,.svid=0x12d1,.apdo_watts=90,.power_watts=90};
    assert(sheng_pps_decide(&p,&s)==SHENG_PPS_UNLOCK);
    s.verifying=true;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_BLOCKED);s.verifying=false;
    s.adapter_id=1;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_NATIVE);s.adapter_id=0;
    p.attempts=3;s.online=false;assert(sheng_pps_decide(&p,&s)==SHENG_PPS_OFFLINE && !p.attempts);
    prime(&b);run(&b);assert(writes==1 && notifications==2 && last_delay==5*HZ && !b.sheng_pps.attempts);
    run(&b);assert(writes==1); /* existing one is monitored but never rewritten */
    /* Repeated firmware clears do not consume the successful-write budget. */
    for(int i=0;i<8;i++){b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=0;run(&b);}
    assert(writes==9 && !b.sheng_pps.attempts);
    /* Actual batterysecret sequence: verify1 -> verify0 -> sysfs0 -> immediate restore. */
    assert(verify_process_store(&b.battery_class,NULL,"1",1)==1 && b.sheng_pps_epoch==1 && last_delay==0);
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(!writes);
    assert(verify_process_store(&b.battery_class,NULL,"0",1)==1 && b.sheng_pps_epoch==2 && last_delay==0);
    assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1 && last_delay==0);
    writes=0;run(&b);assert(writes==1);
    /* Disabling automatic mode keeps a manual zero; no replug required. */
    sheng_pps_auto_verify=false;assert(pd_verifed_store(&b.battery_class,NULL,"0",1)==1);
    writes=0;reads=0;run(&b);assert(!writes && !reads);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_ONLINE]=0;run(&b);assert(!writes && !scheduled && !b.sheng_pps.connected);
    reset(&b);b.psy_list[PSY_TYPE_USB].prop[USB_REAL_TYPE]=2;run(&b);assert(!writes && !scheduled);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes && reads==3);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_ID]=0xa819;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x2717;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=90;run(&b);assert(writes==1); /* captured Huawei */
    for(int svid=0;svid<=1;svid++){
        reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=svid?0x2717:0;
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=100;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=120;run(&b);assert(!writes);
        b.psy_list[PSY_TYPE_XM].prop[XM_PROP_PD_VERIFED]=1;run(&b);assert(!writes);
    }
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_CURRENT_STATE]=25;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_VERIFY_PROCESS]=1;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_POWER_MAX]=100;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_ADAPTER_SVID]=0x291a;b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=140;run(&b);assert(writes==1);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_APDO_MAX]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_SLAVE_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_AUTHENTIC]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_BATTERY_ADAPT_POWER_MATCH]=0;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_BATTERY].prop[BATT_HEALTH]=2;run(&b);assert(!writes);
    reset(&b);b.psy_list[PSY_TYPE_XM].prop[XM_PROP_INPUT_SUSPEND]=1;run(&b);assert(!writes);
    prime(&b);drop_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);native_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);notify_at=14;run(&b);assert(!writes && !notifications && last_delay==0);
    prime(&b);disable_at=14;run(&b);assert(!writes && !notifications);
    prime(&b);unplug_on_write=1;run(&b);assert(writes==1 && !notifications);
    prime(&b);write_rc=-EIO;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && b.sheng_pps.attempts==3 && !notifications);
    prime(&b);ack_one=0;run(&b);run(&b);run(&b);run(&b);assert(writes==3 && !notifications);
    reset(&b);remote_rc=-ETIMEDOUT;run(&b);run(&b);run(&b);assert(!writes && b.sheng_pps.attempts==3);
    reset(&b);b.state=0;run(&b);assert(!reads && !writes && !scheduled);
    reset(&b);b.debug_battery_detected=b.block_tx=true;run(&b);assert(!reads && !writes);
    reset(&b);b.sheng_pps_stopping=true;run(&b);sheng_pps_kick(&b);assert(!reads && !writes && !scheduled);
    prime(&b);b.sheng_pps.attempts=3;b.sheng_pps_reset=1;run(&b);assert(writes==1 && !b.sheng_pps.attempts);
    assert(pd_verifed_store(&b.battery_class,NULL,"bad",3)==-EINVAL);
    b.state=0;assert(pd_verifed_store(&b.battery_class,NULL,"1",1)==-ENOTCONN);
    puts("r87 production PPS policy/worker/store: batterysecret zero recovery, native100->120 priority, immediate events, verified monitoring, repeated clears, protection gates and bounded consecutive failures passed");
    return 0;
}
