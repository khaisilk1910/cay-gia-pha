"""Constants for the Cây Gia Phả integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "cay_gia_pha"
NAME = "Cây Gia Phả"
PLATFORMS: list[Platform] = [Platform.SENSOR]

DATA_DIR_NAME = "cay_gia_pha"
DATABASE_FILENAME = "cay_gia_pha.db"
DATABASE_SCHEMA_VERSION = 5
SUBENTRY_TYPE_PERSON = "person"

FRONTEND_STATIC_URL = "/cay_gia_pha_static"
FRONTEND_CARD_FILENAME = "cay-gia-pha-card.js"
FRONTEND_MODULE_URL = f"{FRONTEND_STATIC_URL}/{FRONTEND_CARD_FILENAME}"
IMAGE_API_URL = "/api/cay_gia_pha/image/{entry_id}/{person_id}"
UPLOAD_PREVIEW_API_URL = "/api/cay_gia_pha/upload_preview/{file_id}"
WS_TYPE_GET_TREE = "cay_gia_pha/get_tree"

CONF_TREE_NAME = "tree_name"
CONF_PERSON_ID = "person_id"
CONF_FULL_NAME = "full_name"
CONF_GENDER = "gender"
CONF_BIRTH_DATE = "birth_date"
CONF_BIRTH_YEAR = "birth_year"
CONF_BIRTH_MONTH = "birth_month"
CONF_BIRTH_DAY = "birth_day"
CONF_DEATH_DATE = "death_date"
CONF_DEATH_YEAR = "death_year"
CONF_DEATH_MONTH = "death_month"
CONF_DEATH_DAY = "death_day"
CONF_IS_DECEASED = "is_deceased"
CONF_LEVEL = "level"

# Structured family relationships used from database schema version 2 onward.
CONF_FATHER_ID = "father_id"
CONF_MOTHER_ID = "mother_id"
CONF_SPOUSE_ID = "spouse_id"
CONF_SPOUSE_IDS = "spouse_ids"
CONF_SPOUSE_ORDER = "spouse_order"
CONF_DIVORCED_SPOUSE_IDS = "divorced_spouse_ids"
CONF_STEP_PARENT_IDS = "step_parent_ids"
CONF_SIBLING_IDS = "sibling_ids"
CONF_BIRTH_ORDER = "birth_order"
CONF_IS_ADOPTED = "is_adopted"

# Retained for compatibility with version 0.1.x data.
CONF_RELATED_PERSON_ID = "related_person_id"
CONF_RELATIONSHIP = "relationship"

CONF_DETAILS = "details"
CONF_IMAGE_PATH = "image_path"
CONF_IMAGE_UPLOAD = "image_upload"
CONF_SORT_ORDER = "sort_order"
CONF_CREATED_AT = "created_at"
CONF_UPDATED_AT = "updated_at"

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_OTHER = "other"
GENDERS = (GENDER_MALE, GENDER_FEMALE, GENDER_OTHER)

RELATION_CHILD = "child"
RELATION_ADOPTED_CHILD = "adopted_child"
RELATION_SPOUSE = "spouse"
RELATION_PARENT = "parent"
RELATION_SIBLING = "sibling"
RELATION_OTHER = "other"
RELATIONSHIPS = (
    RELATION_CHILD,
    RELATION_ADOPTED_CHILD,
    RELATION_SPOUSE,
    RELATION_PARENT,
    RELATION_SIBLING,
    RELATION_OTHER,
)

MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

RUNTIME_SETUP_DONE = "runtime_setup_done"
