"""生成 kb_pdf 语料 PDF（可正常抽取的电子版）。

用法：
    uv run --with reportlab python scripts/gen_pdf_corpus.py          # 生成全部
    uv run --with reportlab python scripts/gen_pdf_corpus.py --only 10
    uv run --with reportlab python scripts/gen_pdf_corpus.py --only 11
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PDF_DIR = _ROOT / "data/corpus/kb_pdf/pdf"


@dataclass(frozen=True)
class PdfSpec:
    filename: str
    cover_lines: tuple[str, ...]
    sections: tuple[tuple[str, tuple[str, ...]], ...]


HANDBOOK_10 = PdfSpec(
    filename="10-办公设备操作手册.pdf",
    cover_lines=(
        "星云科技",
        "办公设备操作手册",
        "（内部资料 · 行政管理部 / IT 联合发布）",
        "版本：V2.1",
        "生效日期：2026-01-01",
    ),
    sections=(
        (
            "第一章 打印机与复印机",
            (
                "1.1 卡纸处理",
                "若打印机卡纸，请先关闭电源，打开侧盖取出卡纸，再按复位键重启。"
                "仍无法恢复请拨打 IT 服务热线 8001 转 2，或通过飞书联系「IT 服务台」。"
                "严禁强行拖拽卡纸，以免损坏定影组件。",
                "1.2 耗材更换",
                "墨粉/碳粉不足时，行政会在飞书「物资申请」统一补货；"
                "各部门不得自行采购非认证耗材。更换耗材前请佩戴手套，"
                "废粉盒按有害废弃物投放到 15 楼 IT 回收点。",
                "1.3 复印保密文件",
                "标有「内部」「机密」的纸质文件复印，须使用带员工工号水印的复印机（15 楼文印室）。"
                "禁止在公共区域打印机复印客户合同原件；扫描后请立即取走原稿。",
            ),
        ),
        (
            "第二章 会议室与视听设备",
            (
                "2.1 无线投屏",
                "连接公司 Wi-Fi（Xingyun-Office），打开飞书「会议室」应用，选择「无线投屏」，"
                "输入屏幕上的 6 位投屏码即可。请勿使用个人热点投屏。",
                "2.2 视频会议",
                "飞书视频会议默认开启等候室；外部嘉宾需由会议发起人审批入会。"
                "会议室电视若无法唤醒，请检查 HDMI 线是否接在「共享」口，"
                "或重启电视柜下方黑色电源时序器（按一次 Off 再按 On）。",
                "2.3 会议室预定",
                "超过 15 人会议请预定 15 楼多功能厅；预定后 10 分钟未到场，系统会自动释放时段。"
                "如需延长，请在飞书日历中修改结束时间，避免影响下一场会议。",
            ),
        ),
        (
            "第三章 门禁与工牌",
            (
                "3.1 门禁卡补办",
                "门禁卡遗失须在 24 小时内通过飞书「行政服务台」提交补办申请；"
                "补办工本费 50 元，新卡 1 个工作日内可至 15 楼前台领取。",
                "3.2 访客通行",
                "访客由内部员工在飞书「访客预约」发起，访客凭短信二维码在 1 楼闸机扫码进入。"
                "访客不得单独进入研发区（12–14 楼），须由对接人全程陪同。",
                "3.3 工牌佩戴",
                "工牌须佩戴于胸前可见位置；进入机房、财务室等敏感区域须额外刷卡登记。",
            ),
        ),
        (
            "第四章 笔记本电脑与显示器",
            (
                "4.1 设备领用",
                "新员工入职由 IT 在入职当天发放标准配置笔记本（研发岗 MacBook Pro 14，"
                "其他岗位 ThinkPad X1）。领用单在飞书审批「IT 资产领用」中签署。",
                "4.2 外接显示器",
                "工位标配 27 寸显示器一台；如需双屏，请提交「IT 资产申请」说明岗位原因。"
                "禁止使用个人显示器接入公司网络端口（安全策略会封禁未知 MAC）。",
                "4.3 设备归还",
                "离职或转岗须在最后一个工作日归还笔记本、充电器、拓展坞；"
                "IT 验收后会在 2 个工作日内完成数据擦除并更新资产台账。",
            ),
        ),
        (
            "第五章 网络与 VPN",
            (
                "5.1 办公 Wi-Fi",
                "员工 Wi-Fi 名称：Xingyun-Office；认证方式为企业微信/飞书扫码。"
                "访客网络 Xingyun-Guest 仅可访问互联网，禁止访问内网系统。",
                "5.2 VPN 使用",
                "默认 VPN 关闭；远程访问 Git、内网 Wiki 需提交「VPN 开通申请」，"
                "由直属主管与信息安全组双审批。VPN 令牌每 90 天强制轮换一次。",
                "5.3 有线网络",
                "工位网口为千兆；若无法上网，请确认是否已注册 MAC 地址。"
                "注册入口：飞书 IT 服务台 → 网络接入 → 有线 MAC 绑定。",
            ),
        ),
        (
            "第六章 电话与分机",
            (
                "6.1 分机拨打",
                "公司内线直接拨 4 位分机；外线请先拨 9 再拨号码。"
                "IT 服务台分机 8001，行政服务台 8002，前台 8000。",
                "6.2 国际长途",
                "国际长途需部门预算审批；未经批准拨打国际长途将按实际话费从部门经费扣减。",
                "6.3 录音与合规",
                "客服、销售岗位分机默认开启通话录音；其他岗位录音需法务与员工书面确认。",
            ),
        ),
        (
            "第七章 常见问题 FAQ",
            (
                "Q: 打印机显示「无法识别硒鼓」怎么办？",
                "A: 取出硒鼓重新安装；若仍报错，更换备用硒鼓并联系 IT 8001 登记耗材型号。",
                "Q: 会议室电视黑屏？",
                "A: 先按遥控器电源键；无效则重启时序器；仍无效在飞书「行政服务台」报障。",
                "Q: 笔记本忘记开机密码？",
                "A: 携带工牌到 15 楼 IT 服务台重置；重置后须当场修改密码并启用双因素认证。",
                "Q: 能否安装个人软件？",
                "A: 禁止安装未在「软件白名单」内的程序；开发工具请使用 IT 提供的标准镜像。",
            ),
        ),
    ),
)

# 主题：园区后勤 / 物业 / 应急 —— 与 internal 制度、10 号设备手册不重叠
HANDBOOK_11 = PdfSpec(
    filename="11-园区设施与后勤服务手册.pdf",
    cover_lines=(
        "星云科技",
        "园区设施与后勤服务手册",
        "（内部资料 · 物业与行政联合发布）",
        "版本：V1.0",
        "生效日期：2026-03-01",
    ),
    sections=(
        (
            "第一章 地下停车场与车辆管理",
            (
                "1.1 车位分配",
                "园区地下停车场分为 B1（员工固定车位）、B2（访客临时车位）两层。"
                "固定车位通过年度抽签分配，中签员工须在飞书「车位管理」绑定车牌号；"
                "未中签员工可使用 B2 先到先得车位，单日停放上限 10 小时。",
                "1.2 临停与访客停车",
                "访客车辆须由对接员工在飞书「访客预约」同步登记车牌；"
                "访客凭短信二维码在 B2 入口闸机抬杆。临停费率：首 2 小时免费，"
                "之后每半小时 5 元，单日封顶 40 元，费用由接待部门承担。",
                "1.3 违停处理",
                "占用消防通道、充电桩专用位或未绑定车牌驶入 B1 固定区域的，"
                "物业将张贴提醒单；累计 3 次违停将取消当年固定车位抽签资格。",
            ),
        ),
        (
            "第二章 非机动车与充电设施",
            (
                "2.1 自行车停放",
                "大厦东侧设封闭式非机动车库，凭工牌刷卡进入。"
                "禁止将电动车、自行车停放在大堂、楼梯间或消防疏散通道；"
                "违规停放物品将被移至 1 楼失物区，停放满 7 日无人认领按废弃物处理。",
                "2.2 电动车充电",
                "园区内仅 B1 层 E 区设有合规充电桩 20 个，最大功率 7kW；"
                "禁止私拉电线或在工位插座为电动车电池充电。"
                "充电须使用「星云充电」小程序扫码，充满后请在 30 分钟内移车。",
                "2.3 共享单车",
                "大厦出入口 50 米范围内禁止停放第三方共享单车；"
                "物业每日 8:00 与 18:00 各清理一次，请配合停放至市政指定区域。",
            ),
        ),
        (
            "第三章 员工餐厅与茶歇区",
            (
                "3.1 餐厅开放时段",
                "15 楼员工餐厅午餐 11:30–13:30，晚餐 17:30–19:30（节假日以公告为准）。"
                "采用自助餐模式，凭工牌刷卡入内；每餐补贴 15 元，超出部分从工资代扣。",
                "3.2 外来人员就餐",
                "外部驻场人员须由对接部门提前在飞书「餐券申请」购买临时餐券，"
                "单价 32 元/餐；未持券者谢绝入内。客户接待餐请走商务接待流程，"
                "不得在员工餐厅签单招待。",
                "3.3 茶歇与微波炉",
                "各楼层茶水间提供微波炉 2 台、冰箱 1 台；"
                "食品须贴姓名与日期标签，存放不得超过 3 天。"
                "物业每周五 17:00 清理未标注或过期食品，请勿存放气味强烈的食物。",
            ),
        ),
        (
            "第四章 健身与休闲设施",
            (
                "4.1 健身房使用",
                "16 楼健身中心对全员开放，时间为工作日 7:00–22:00，周末 9:00–18:00。"
                "首次使用须在飞书「健身中心」完成安全须知签署；"
                "使用器械后请擦拭汗渍，穿胶底运动鞋入场，禁止赤脚或穿拖鞋。",
                "4.2 淋浴与更衣",
                "健身中心配套男女更衣室各一，提供热水淋浴；"
                "请自备毛巾与拖鞋，储物柜钥匙当日 22:30 前归还，"
                "过夜物品由物业统一开柜并登记认领。",
                "4.3 乒乓球与台球",
                "16 楼休闲区设乒乓球台 2 张、台球桌 1 张；"
                "通过飞书「设施预约」抢占时段，单次最长 60 分钟，"
                "超时 15 分钟未让出将记入爽约记录，累计 3 次暂停预约 7 天。",
            ),
        ),
        (
            "第五章 消防安全与疏散",
            (
                "5.1 疏散路线",
                "办公区疏散图张贴于各楼层电梯厅；发生火灾时禁止乘坐电梯，"
                "请沿绿色「安全出口」指示牌前往最近疏散楼梯。"
                "15 楼集合点位于大厦南侧广场旗杆处，部门点名由楼层安全员负责。",
                "5.2 消防器材",
                "每 50 米配置灭火器 1 组；消防栓内水带仅供培训与应急使用，"
                "非火情不得擅自开箱。发现灭火器压力表指针处于红色区域，"
                "请通过飞书「物业报修」上报。",
                "5.3 消防演练",
                "全楼消防疏散演练每年 5 月与 11 月各举行一次；"
                "演练当日 10:00–10:30 警报响起时，请立即停止作业有序撤离。"
                "因出差未参加者须在下月补训并签到。",
            ),
        ),
        (
            "第六章 恶劣天气与突发停水停电",
            (
                "6.1 台风与暴雨",
                "气象台发布橙色及以上预警时，物业将关闭 B2 露天坡道并在大堂铺设防滑垫。"
                "请收好窗台物品，下班前关闭窗户。地下停车场可能临时封闭，"
                "以飞书「物业通知」群公告为准。",
                "6.2 计划性停电",
                "配电室检修须提前 3 个工作日发邮件与飞书公告；"
                "机房、实验室等关键区域由物业配合柴油发电机保障，"
                "其他工位请保存文档并关闭电脑，停电期间电梯暂停使用。",
                "6.3 突发停水",
                "停水期间 1 楼大厅提供临时饮用水；卫生间暂停使用，"
                "请前往未受影响楼层。恢复供水后前 5 分钟可能水质浑浊，"
                "建议先放清后再饮用。",
            ),
        ),
        (
            "第七章 垃圾分类与旧物回收",
            (
                "7.1 四分类标准",
                "工位旁垃圾桶仅投放干垃圾；茶水间设湿垃圾（厨余）桶；"
                "打印废纸箱请压扁后投至楼层回收点蓝色筐；"
                "硒鼓、电池、灯管等有害废弃物投至 15 楼 IT 回收点，"
                "不得混入普通垃圾。",
                "7.2 废旧电子设备",
                "报废键盘、鼠标、排插等办公小电器请放入 15 楼 IT 回收柜；"
                "含硬盘、内存的整机须走 IT 资产报废流程，"
                "由 IT 统一消磁后交物业环保处置。",
                "7.3 旧书旧衣捐赠",
                "行政每季度末在 1 楼大堂设立旧物捐赠箱，"
                "接受干净衣物与书籍；捐赠清单在飞书「公益捐赠」公示去向。",
            ),
        ),
        (
            "第八章 通勤班车与加班交通",
            (
                "8.1 早晚班车线路",
                "园区开通三条免费班车：A 线（张江地铁站）、B 线（世纪大道地铁站）、"
                "C 线（莘庄地铁站）。发车时刻表张贴于 1 楼大堂，"
                "须刷工牌乘车，非员工不得搭乘。",
                "8.2 加班班车",
                "工作日 21:30 增发一班夜班班车，路线同 A 线；"
                "22:30 后离园请使用企业打车（飞书「夜间出行」），"
                "上限 50 元/次，超出部分自理。",
                "8.3 班车准点",
                "班车发车后 2 分钟关门，运行中不停靠临时站点；"
                "遇交通拥堵请在飞书群查看司机实时位置，"
                "勿在车道上追赶班车。",
            ),
        ),
        (
            "第九章 母婴室与无障碍设施",
            (
                "9.1 母婴室",
                "8 楼与 15 楼各设母婴室一间，含哺乳椅、洗手池、冰箱与尿布台；"
                "使用前后请登记并通风，禁止堆放私人物品过夜。",
                "9.2 无障碍通道",
                "大厦各入口均有无障碍坡道；低层消防楼梯配备轮椅升降平台，"
                "使用前请联系前台 8000 安排物业人员协助。",
                "9.3 爱心座位",
                "餐厅与班车设爱心专座；孕妇、行动不便者优先使用，"
                "其他员工请勿长期占用。",
            ),
        ),
        (
            "第十章 失物招领与寄存服务",
            (
                "10.1 失物招领",
                "在大厦内拾获物品请交 1 楼前台失物招领处；"
                "物业每日 18:00 在飞书「失物招领」群发布清单。"
                "贵重物品（手机、钱包、笔记本）保管 90 日，"
                "普通物品 30 日，逾期按废弃处理。",
                "10.2 临时寄存柜",
                "1 楼大堂设自助寄存柜 40 格，扫码使用，"
                "首 4 小时免费，之后每 2 小时 2 元。"
                "禁止存放易燃易爆、鲜活易腐物品；"
                "超过 48 小时未取，物业有权开柜处理。",
                "10.3 大件物品进出",
                "搬运显示器、机箱等大件进出大厦须在飞书「物品放行条」"
                "登记并由保安扫码放行；非工作时间（22:00–8:00）"
                "须经行政主管审批。",
            ),
        ),
        (
            "第十一章 绿化养护与屋顶花园",
            (
                "11.1 屋顶花园开放",
                "17 楼屋顶花园在每年 4 月至 10 月对全员开放，"
                "工作日 12:00–13:30、17:30–19:00 两个时段可预约进入。"
                "每次预约不超过 20 人，通过飞书「屋顶花园」抢号，"
                "请爱护花卉，禁止采摘与践踏草坪。",
                "11.2 室内绿植",
                "办公区绿萝、发财树等绿植由物业每两周养护一次；"
                "若植物枯萎或盆土发臭，请在飞书「物业报修」说明楼层与工位号，"
                "物业将在 2 个工作日内更换。员工不得自行浇灌过量或投放肥料。",
                "11.3 蚊虫与消杀",
                "物业每月第一个周六非办公时间进行全楼灭虫消杀；"
                "消杀当日请关闭门窗并收起食品。对蚊虫叮咬过敏者，"
                "可向行政领取防蚊液，前台备有少量花露水供临时使用。",
            ),
        ),
    ),
)

_SPECS: dict[str, PdfSpec] = {
    "10": HANDBOOK_10,
    "11": HANDBOOK_11,
}


def _pick_font() -> Path:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("未找到中文字体，请在本机 macOS 运行或修改字体路径。")


def _draw_paragraph(c, font_name: str, text: str, *, x: float, y: float, width: float, size: int = 11) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    c.setFont(font_name, size)
    line_height = size * 1.6
    buf: list[str] = []
    for ch in text:
        trial = "".join(buf + [ch])
        if stringWidth(trial, font_name, size) <= width:
            buf.append(ch)
        else:
            if buf:
                c.drawString(x, y, "".join(buf))
                y -= line_height
            buf = [ch]
    if buf:
        c.drawString(x, y, "".join(buf))
        y -= line_height
    return y


def _body_char_count(spec: PdfSpec) -> int:
    return sum(len(p) for _title, paras in spec.sections for p in paras)


def build_pdf(spec: PdfSpec, out_path: Path) -> int:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_path = _pick_font()
    font_name = "CorpFont"
    pdfmetrics.registerFont(TTFont(font_name, str(font_path), subfontIndex=0))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    margin_x = 50
    content_width = width - 2 * margin_x

    y = height - 120
    for i, line in enumerate(spec.cover_lines):
        size = 28 if i == 0 else 22 if i == 1 else 12
        c.setFont(font_name, size)
        c.drawString(margin_x, y, line)
        y -= size * 2
    c.showPage()

    y = height - 60
    c.setFont(font_name, 18)
    c.drawString(margin_x, y, "目录")
    y -= 36
    c.setFont(font_name, 12)
    for idx, (title, _) in enumerate(spec.sections, 1):
        c.drawString(margin_x + 10, y, f"{idx}. {title}")
        y -= 22
        if y < 60:
            c.showPage()
            y = height - 60
    c.showPage()

    for title, paragraphs in spec.sections:
        y = height - 60
        c.setFont(font_name, 16)
        c.drawString(margin_x, y, title)
        y -= 32
        for para in paragraphs:
            y = _draw_paragraph(c, font_name, para, x=margin_x, y=y, width=content_width, size=11)
            y -= 8
            if y < 80:
                c.showPage()
                y = height - 60
        c.showPage()

    c.save()
    return c.getPageNumber()


def generate(spec: PdfSpec) -> Path:
    out = _PDF_DIR / spec.filename
    pages = build_pdf(spec, out)
    chars = _body_char_count(spec)
    print(f"已生成: {out}")
    print(f"  章节: {len(spec.sections)}  正文约 {chars} 字  页数: {pages}")
    return out


def main() -> None:
    try:
        import reportlab  # noqa: F401
    except ImportError as exc:
        raise SystemExit("请运行: uv run --with reportlab python scripts/gen_pdf_corpus.py") from exc

    parser = argparse.ArgumentParser(description="生成 kb_pdf 语料 PDF")
    parser.add_argument(
        "--only",
        choices=sorted(_SPECS),
        default=None,
        help="只生成指定编号（10=设备手册, 11=园区后勤）",
    )
    args = parser.parse_args()

    keys = [args.only] if args.only else sorted(_SPECS)
    for key in keys:
        generate(_SPECS[key])


if __name__ == "__main__":
    main()
