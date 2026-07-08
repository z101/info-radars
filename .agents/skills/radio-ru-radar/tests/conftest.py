import sys
from pathlib import Path

import pytest

_skill_root = Path(__file__).parent.parent
_src = _skill_root / "src"
sys.path.insert(0, str(_skill_root))
sys.path.insert(0, str(_src))


@pytest.fixture
def sample_content_october_2025() -> str:
    return """<!DOCTYPE html>
<html><body>
<h4>Содержание номера</h4>
<table border="0" cellspacing="0" cellpadding="0" align="center" class="t_sod">
<tr><td style="column-span: 2; padding: 3px" align=center><b>&mdash;</b></td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Наука и техника</b></td></tr>
<tr><td><b>А. ГОЛЫШКО.</b> Улучшая 5G. <a href="/arhiv/2025/10/V/d3b87ed2c2fe4b640ddb8c91547118d1.shtml"><img src="/arhiv/img/d1.gif"></a></td><td>4</td></tr>
<tr><td><b>Я. БЛАГУШИН.</b> О влиянии на организм человека продолжительных доз СВЧ-излучения небольшой мощности (по материалам зарубежной прессы). <a href="/arhiv/2025/10/V/eab47e2975b7c63b9b61e649a06f9438.shtml"><img src="/arhiv/img/d.gif"></a></td><td>8</td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Радиоприем</b></td></tr>
<tr><td><b>В. ШЕПТУХИН.</b> Новости вещания. <a href="/arhiv/2025/10/V/f3f33196d718ba5e25d856fca53efd5d.shtml"><img src="/arhiv/img/d1.gif"></a></td><td>11</td></tr>
<tr><td><b>Х. ЛОХНИ.</b> Новый УВЧ-УПЧ для приёмников «Океан-209» и Selena. <a href="/arhiv/2025/10/V/5989d1f7600532353d9325944d6c737b.shtml"><img src="/arhiv/img/d.gif"></a></td><td>13</td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Измерения</b></td></tr>
<tr><td><b>А. КУЗЬМИНОВ.</b> Вольтметр действующего и средневыпрямленного значений напряжения. <a href="/arhiv/2025/10/V/01c9c0881bee8bbae8a7e85753e95e91.shtml"><img src="/arhiv/img/d.gif"></a></td><td>24</td></tr>
</table>
<h4>Октябрь</h4>
</body></html>"""


@pytest.fixture
def sample_content_april_2026() -> str:
    return """<!DOCTYPE html>
<html><body>
<h4>Содержание номера</h4>
<table border="0" cellspacing="0" cellpadding="0" align="center" class="t_sod">
<tr><td style="column-span: 2; padding: 3px" align=center><b>&mdash;</b></td></tr>
<tr><td><b></b> Информация нашим авторам. <a href="/arhiv/2026/4/V/5ee2eec4e532e01cd60ae001c35b09e4.shtml"><img src="/arhiv/img/d.gif"></a></td><td>30</td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Наука и техника</b></td></tr>
<tr><td><b>А. ГОЛЫШКО.</b> Сумерки над заводами. <a href="/arhiv/2026/4/V/024363c0b31e21ade0326cbc57a9a418.shtml"><img src="/arhiv/img/d1.gif"></a></td><td>4</td></tr>
<tr><td><b>Я. БЛАГУШИН.</b> &laquo;О влиянии на организм человека продолжительных доз СВЧ-излучения небольшой мощности (по материалам зарубежной прессы)&raquo;. <a href="/arhiv/2026/4/V/fa47c2264db74d23ec24ec3855197fd0.shtml"><img src="/arhiv/img/d.gif"></a></td><td>8</td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Радиоприем</b></td></tr>
<tr><td><b>Х. ЛОХНИ.</b> Приёмники &laquo;Океан&raquo;/Selena. Новые диапазонные планки. <a href="/arhiv/2026/4/V/c88c536d5b9dcac39c9961bcff87975a.shtml"><img src="/arhiv/img/d.gif"></a></td><td>10</td></tr>
<tr><td><b>В. ШЕПТУХИН.</b> Новости вещания. <a href="/arhiv/2026/4/V/db030ab75cdb337f4e2f855b2b804e60.shtml"><img src="/arhiv/img/d1.gif"></a></td><td>21</td></tr>
<tr><td style="column-span: 2; padding: 3px" align=center><b>Звукотехника</b></td></tr>
<tr><td><b>И. РОГОВ.</b> Устройство защиты громкоговорителей от постоянного напряжения на выходе усилителя. <a href="/arhiv/2026/4/V/dc643c0c1583bd77e9fb586499e249cc.shtml"><img src="/arhiv/img/d.gif"></a></td><td>27</td></tr>
</table>
<h4>Апрель</h4>
</body></html>"""


@pytest.fixture
def sample_excerpt_html() -> str:
    return """<!DOCTYPE html>
<html><body>
<h4>Аннотация статьи</h4>
<table border="0" cellspacing="0" cellpadding="0" align="center" class="t_sod">
<td width=100% valign=top align=justify><p><b>Х. ЛОХНИ.</b> Новый УВЧ-УПЧ для приёмников «Океан-209» и Selena.</p></td></tr>
<td width=100% valign=top align=justify style="padding: 1px; border-bottom-style:solid; border-width:1px; border-color: #f0f0f0"><p>В этой части статьи обсуждаются вопросы подбора радиоэлементов. Новый УВЧ-УПЧ позволит задействовать старые запасы катушек индуктивности, транзисторов и диодов, осталось их проверить и подобрать. Качество приёма существенно зависит от пьезокерамических фильтров (ПКФ), и без их тщательного отбора проект не реализовать. Приведены советы и примеры по этому вопросу.</p>
<p><a href="http://ftp.radio.ru/pub/2025/10/13.pdf">Прочитать</a></p></td></tr>
<td width=100% valign=bottom align=center><font size=2 face=Arial><br><a href="/arhiv/2025/10.shtml"><b>Вернуться назад.</b></a></font></td></tr>
</table>
</body></html>"""


@pytest.fixture
def sample_excerpt_with_pdf_html() -> str:
    return """<!DOCTYPE html>
<html><body>
<h4>Аннотация статьи</h4>
<table border="0" cellspacing="0" cellpadding="0" align="center" class="t_sod">
<td width=100% valign=top align=justify><p><b>А. ГОЛЫШКО.</b> Улучшая 5G.</p></td></tr>
<td width=100% valign=top align=justify style="padding: 1px; border-bottom-style:solid; border-width:1px; border-color: #f0f0f0"><p>Казалось бы, 2019 г. был совсем недавно и запомнился он развёртыванием совершенно новых на тот момент сетей мобильной связи пятого поколения (5G), о начале развития которых уже шла речь на страницах журнала.</p>
<p><a href="http://ftp.radio.ru/pub/2025/10/4.pdf">Прочитать</a></p></td></tr>
<td width=100% valign=bottom align=center><font size=2 face=Arial><br><a href="/arhiv/2025/10.shtml"><b>Вернуться назад.</b></a></font></td></tr>
</table>
</body></html>"""


@pytest.fixture
def sample_empty_content() -> str:
    return """<!DOCTYPE html>
<html><body>
<p>No content here</p>
</body></html>"""


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test_radio.db")


@pytest.fixture
def sample_archive_toc_1994() -> str:
    return """<html>
<head><meta http-equiv="CONTENT-TYPE" content="text/html; charset=koi8-r">
<title>Журнал "Радио" | Содержание | Январь 1994</title></head>
<body>
<h4>Содержание номера</h4>
<table border=0 cellspacing=0 cellpadding=0 width="100%">
<tr><td width="93%"><b>А. Петров.</b> Новая схема</td><td width="7%">5</td></tr>
<tr><td colspan="2" align=center><b>Радиоприем</b></td></tr>
<tr><td width="93%"><b>И. Иванов.</b> Усилитель для приемника</td><td width="7%">12</td></tr>
<tr><td width="93%"><b>В. Сидоров.</b> Простой детектор</td><td width="7%">15</td></tr>
</table>
</body></html>"""


@pytest.fixture
def sample_archive_annot_2002() -> str:
    return """<html>
<head><meta http-equiv="CONTENT-TYPE" content="text/html; charset=koi8-r">
<title>Журнал "Радио" | Содержание | Январь 2002</title>
<script>
function opendescription(id){
window.open ('http://www.radio.ru/archive/2002/01/a' + id + '.shtml', 'Description', 'height=300, width=250, resizable=1, scrollbars=yes, menubar=no, status=no');
}
</script>
</head>
<body>
<h4>Содержание номера</h4>
<table border=0 cellspacing=0 cellpadding=0 width="100%">
<tr><td width="93%">Поздравляем2001 <a href="javascript:opendescription(1);"><img src="/images/d.gif" width=15 height=15 border=0></a></td><td width="7%">4</td></tr>
<tr><td colspan="2" align=center><b>Радиоприем</b></td></tr>
<tr><td width="93%"><b>А. Петров.</b> Новый приемник <a href="javascript:opendescription(2);"><img src="/images/d.gif" width=15 height=15 border=0></a></td><td width="7%">6</td></tr>
<tr><td width="93%"><b>И. Сидоров.</b> Усилитель для УКВ <a href="javascript:opendescription(3);"><img src="/images/d.gif" width=15 height=15 border=0></a></td><td width="7%">8</td></tr>
</table>
</body></html>"""


@pytest.fixture
def sample_archive_djvu_2005() -> str:
    return """<html>
<head><meta http-equiv="CONTENT-TYPE" content="text/html; charset=koi8-r">
<title>Журнал "Радио" | Содержание | Январь 2005</title>
<script>
function opendescription(id){
window.open ('http://www.radio.ru/archive/2005/01/a' + id + '.shtml', 'Description', 'height=640, width=480, resizable=1, scrollbars=yes, menubar=yes, status=no');
}
</script>
</head>
<body>
<h4>Содержание номера</h4>
<table border=0 cellspacing=0 cellpadding=0 width="100%">
<tr><td width="93%">С Новым годом! <a href="javascript:opendescription(1);"><img src="/images/d1.gif" width=15 height=15 border=0></a></td><td width="7%">4</td></tr>
<tr><td colspan="2" align=center><b>Наука и техника</b></td></tr>
<tr><td width="93%"><b>А. Голышко.</b> Тенденции в технологиях <a href="javascript:opendescription(2);"><img src="/images/d1.gif" width=15 height=15 border=0></a></td><td width="7%">8</td></tr>
<tr><td width="93%"><b>И. Иванов.</b> Обзор телевизоров <a href="javascript:opendescription(3);"><img src="/images/d.gif" width=15 height=15 border=0></a></td><td width="7%">10</td></tr>
</table>
</body></html>"""


@pytest.fixture
def sample_archive_pdf_2009() -> str:
    return """<html>
<head><meta http-equiv="CONTENT-TYPE" content="text/html; charset=koi8-r">
<title>Журнал "Радио" | Содержание | Декабрь 2009</title>
<script>
function opendescription(id){
window.open ('http://www.radio.ru/archive/2009/12/a' + id + '.shtml', 'Description', 'height=640, width=480, resizable=1, scrollbars=yes, menubar=yes, status=no');
}
</script>
</head>
<body>
<h4>Содержание номера</h4>
<table border=0 cellspacing=0 cellpadding=0 width="100%">
<tr><td width="93%">К 150-летию А. С. Попова <a href="javascript:opendescription(1);"><img src="/images/d1.gif" width=15 height=15 border=0></a></td><td width="7%">4</td></tr>
<tr><td colspan="2" align=center><b>Радиоприем</b></td></tr>
<tr><td width="93%"><b>В. Поляков.</b> Радиовещание на УКВ <a href="javascript:opendescription(2);"><img src="/images/d1.gif" width=15 height=15 border=0></a></td><td width="7%">8</td></tr>
<tr><td width="93%"><b>И. Нечаев.</b> Источник питания <a href="javascript:opendescription(3);"><img src="/images/d.gif" width=15 height=15 border=0></a></td><td width="7%">16</td></tr>
</table>
</body></html>"""