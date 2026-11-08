"""Vietnamese test inputs. Generated ads are Vietnamese, so guards must be tested on Vietnamese text."""

SAFE_HOOK = "Xe điện cho gia đình trẻ"
SAFE_BODY = "Chỉ từ {{price_vnd:VF3:eco:battery_included}} cho bản Eco, đi được xa mỗi ngày."
RANGE_BODY = "Tầm hoạt động lên đến {{range_km:VF3:eco}} km theo chuẩn {{range_km_standard:VF3:eco}}."
SAFE_CTA = "Đăng ký lái thử"
SMS_BODY = "VF3 cho gia đình trẻ, đăng ký lái thử ngay hôm nay."
PLAN_MESSAGE = "Xe điện nhỏ gọn cho gia đình trẻ"
PLAN_RATIONALE = "Phân khúc gia đình trẻ quan tâm tới chi phí hằng ngày."
BANNED_PHRASE = "tốt nhất"
BANNED_TEXT = "Đây là chiếc xe tốt nhất."
PROMOTION_TEXT = "Ưu đãi lớn đến 31/12/2030 cho khách hàng."
OBJECTION = "Xe điện có đắt không"
OBJECTION_RESPONSE = "Nói về tổng chi phí"
OBJECTION_MISTAKE = "Né câu hỏi"

EDITED_HOOK = "Xe điện mới cho gia đình trẻ"
EDITED_SMS_BODY = "VF3 rộng rãi cho gia đình trẻ, mời bạn lái thử cuối tuần này."
RESOLVED_PRICE = "235.000.000đ"
RANGE_STANDARD_AS_DISTANCE = "Tầm hoạt động lên đến {{range_km_standard:VF3:eco}} theo chuẩn đó."
RANGE_WITHOUT_UNIT = "Tầm hoạt động lên đến {{range_km:VF3:eco}} theo chuẩn {{range_km_standard:VF3:eco}}."
PRICE_WITH_CURRENCY_WORD = "Chỉ từ {{price_vnd:VF3:eco:battery_included}} đồng cho bản Eco."
TYPED_WRONG_PRICE = "500.000.000đ"
TYPED_RIGHT_PRICE = "646.000.000đ"

RAW_NUMBER_CASES = [
    ("Giá chỉ 299.000.000 đồng", ["299.000.000"]),
    ("Chỉ 322 triệu", ["322 triệu"]),
    ("Tiết kiệm 70%", ["70%"]),
    ("Đi được 210 km", ["210 km"]),
    ("Pin 18,64 kWh", ["18,64 kWh"]),
    ("Bảo hành 7 năm", ["Bảo hành 7 năm"]),
    ("Hàng ngàn người đã chọn", ["Hàng ngàn người"]),
]
CLEAN_NUMBER_CASES = [
    "Gọi tổng đài 1900.232.389",
    "Xe 5 chỗ, sạc 5 giờ",
    "Đi hàng ngàn cây số",
    "Chương trình từ 10/09/2026",
]

NATURAL_BRIEF = (
    "Chiến dịch lái thử VF3 cho người 25-35 tuổi, đang so sánh các mẫu xe, "
    "đăng trên fanpage và tin nhắn từ 10/09/2030 đến 20/09/2030"
)
