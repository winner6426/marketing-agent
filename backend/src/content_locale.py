"""Vietnamese vocabulary matched in, or added to, generated ad content.

Ads stay Vietnamese, so these literals are data. This is the only source file allowed to contain Vietnamese.
"""

# --- Brief interpretation: words a marketer may type ---------------------------
CHANNEL_ALIASES = {"tin nhắn": "direct_message", "tin_nhan": "direct_message"}
EMPTY_ANSWER_WORDS = ("chưa rõ", "không rõ")

DATE_RANGE_PREFIXES = "từ"
DATE_RANGE_SEPARATORS = "đến|tới"
MONTH_RANGE_PATTERN = r"\btrong\s+tháng\s+(\d{1,2})\s*[/\-]\s*(\d{4})\b"
AGE_RANGE_PATTERN = (
    r"(?:people\s+aged|người|khách\s*hàng)?\s*(?:from|từ)?\s*(\d{1,2})\s*"
    r"(?:-|–|—|to|đến|tới)\s*(\d{1,2})\s*(?:years?\s*old|tuổi)"
)

TEST_DRIVE_WORDS = r"lái\s*thử"
LAUNCH_WORDS = r"ra\s*mắt"
PROMOTION_WORDS = r"khuyến\s*mãi|ưu\s*đãi"

READY_TO_BUY_WORDS = r"sắp\s+chốt|đặt\s+cọc|mua\s+ngay"
CONSIDERING_WORDS = r"cân\s+nhắc|so\s+sánh|tìm\s+hiểu"
AWARENESS_WORDS = r"nhận\s+biết|mới\s+biết"
DIRECT_MESSAGE_WORDS = r"tin\s*nhắn"

# --- Brief clarification: questions shown to the marketer in the chat ----------
BRIEF_QUESTIONS = {
    "goal": "Mục tiêu của chiến dịch là gì: ra mắt (launch), lái thử (test_drive) hay khuyến mãi (promotion)?",
    "model_missing": "Chiến dịch này dành cho mẫu xe nào? Hiện có: {available}.",
    "model_unknown": "Mẫu xe '{model_id}' không có trong danh mục. Hiện có: {available}. Bạn muốn chọn mẫu nào?",
    "catalog_empty": "danh mục đang trống",
    "segment": "Chiến dịch hướng tới nhóm khách hàng nào (ví dụ: gia đình trẻ, người yêu công nghệ)?",
    "funnel_stage": (
        "Khách hàng đang ở giai đoạn nào: mới biết đến sản phẩm (awareness), đang so sánh các lựa chọn "
        "(consideration), hay sắp quyết định mua (intent)?"
    ),
    "channels_missing": "Bạn cần nội dung cho những kênh nào? Các kênh hỗ trợ: {supported}.",
    "channels_unsupported": (
        "Các kênh {unsupported} chưa được hỗ trợ. Các kênh hỗ trợ: {supported}. Bạn muốn chọn kênh nào?"
    ),
    "dates": "Chiến dịch chạy trong thời gian nào? Ví dụ: từ 2026-09-10 đến 2026-09-20.",
}

# --- Numeric guard: raw number shapes in generated text ------------------------
LETTER_RANGE = "A-Za-zÀ-ỹ"
UNIT_WORD_RANGE = "A-Za-zÀ-ỹđĐ"

CURRENCY_NUMBER_PATTERN = (
    r"(?<![\w.,])~?\s*\d+(?:[.,]\d+)?\s*(?:đ(?:ồng)?|vnđ|vnd)(?:\s*/\s*km)?\b"
    r"|(?<![\w.,])~?\s*\d+(?:[.,]\d+)?\s*(?:triệu|tỷ|tr|k)\b"
)
WARRANTY_YEARS_PATTERN = (
    r"bảo\s+hành(?:\s+\w+){0,4}\s*[:\-]?\s*\d+(?:[.,]\d+)?\s*năm"
    r"|\d+(?:[.,]\d+)?\s*năm(?:\s+\w+){0,4}\s+bảo\s+hành"
)
# Needs a group of people: "hàng ngàn cây số" is a distance and must stay allowed.
SOCIAL_PROOF_PATTERN = (
    r"hàng\s+(?:chục\s+(?:nghìn|ngàn)|nghìn|ngàn|vạn|triệu|trăm)\s+"
    r"(?:người|khách(?:\s+hàng)?|gia\s+đình|chủ\s+xe|tài\s+xế)\b"
)

YEAR_UNIT = "năm"
WRONG_UNIT_WORDS = ("năm", "tháng", "ngày", "giờ", "km", "kwh", "đồng", "vnđ", "vnd", "chỗ", "ghế")
RANGE_CONTEXT_WORDS = (
    r"tầm\s+hoạt\s+động|quãng\s+đường|đi\s+được|di\s+chuyển\s+được|chạy\s+được|phạm\s+vi\s+hoạt\s+động"
)

# --- Fact checker --------------------------------------------------------------
CURRENCY_SYMBOL = "đ"
PROMOTION_CLAIM_PATTERN = r"\b(?:ưu đãi|khuyến mãi|khuyến mại|giảm giá|quà tặng)\b"

# --- Text the writer appends to a draft ----------------------------------------
AD_LABEL_PATTERN = r"\A\s*\[(?:QC|AD)\]"
AD_LABEL = "[QC]"
OPT_OUT_PATTERN = (
    r"(?:từ chối|tu choi|huỷ nhận|hủy nhận|huy nhan"
    r"|so[aạ]n\s+\w+\s+g[uử]i\s+\d+|nh[aắ]n\s+\w+\s+t[oớ]i\s+\d+)"
    r"\s*[.!?]?\s*\Z"
)
# Deliberately unaccented: one accented letter pushes the whole SMS from GSM-7 to UCS-2.
OPT_OUT_SENTENCE = "Soan TC gui 9999 de tu choi."
RANGE_STANDARD_NOTE = "(Quãng đường đo theo chuẩn {placeholder}.)"

# --- Examples quoted in writer prompts -----------------------------------------
BANNED_SOCIAL_PROOF_EXAMPLES = (
    '"hàng triệu người", "hàng nghìn khách hàng", "hàng ngàn gia đình", "hàng chục nghìn chủ xe", '
    '"hàng vạn/hàng trăm" + người/khách hàng/gia đình/chủ xe/tài xế'
)
VAGUE_SOCIAL_PROOF_EXAMPLE = '"được nhiều người tin dùng"'
RANGE_CORRECT_EXAMPLE = "tầm hoạt động lên đến {{range_km:VF5:plus}} km theo chuẩn {{range_km_standard:VF5:plus}}"
RANGE_WRONG_EXAMPLES = (
    "tầm hoạt động lên đến {{range_km:VF5:plus}} theo chuẩn {{range_km_standard:VF5:plus}}",
    "tầm hoạt động lên đến {{range_km_standard:VF5:plus}}",
)
RANGE_RENDERED_WRONG_EXAMPLE = "lên đến 326,4 theo chuẩn NEDC"
PRICE_CORRECT_EXAMPLE = "chỉ từ {{price_vnd:VF6:eco:battery_included}} cho bản Eco"
PRICE_DOUBLE_UNIT_EXAMPLE = "646.000.000đ đồng"
RANGE_STANDARD_LEAD_IN = "theo chuẩn"
RANGE_WRONG_LEAD_IN = "lên đến"
WARRANTY_NUMBER_EXAMPLES = '"8 năm", "160.000 km", "lên đến 10 năm"'
WARRANTY_GENERIC_EXAMPLE = '"bảo hành theo chính sách hãng"'

# --- Slugs: letters that Unicode NFD does not decompose ------------------------
SLUG_LETTER_MAP = {"đ": "d", "Đ": "d"}

# --- SMS: the GSM 03.38 alphabet, kept verbatim as standard data, not Vietnamese ------
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = "^{}\\[~]|€"
