from bs4 import BeautifulSoup
from flask import render_template


def test_admin_page_exposes_legacy_xls_and_multi_wav_import_controls():
    from potato.flask_server import app

    with app.test_request_context("/admin"):
        html = render_template(
            "admin.html",
            ui_lang={},
            annotation_task_name="测试任务",
            admin_api_key="key",
            debug_mode=False,
            mace_enabled=False,
            bws_enabled=False,
            embedding_viz_enabled=False,
            datasets_enabled=False,
            judge_calibration_enabled=False,
            triage_enabled=False,
            automation_enabled=False,
            curation_enabled=False,
            arena_enabled=False,
        )

    page = BeautifulSoup(html, "html.parser")
    tab = page.select_one('[data-tab="audio-import"]')
    excel = page.select_one('#audioImportExcel')
    audio = page.select_one('#audioImportFiles')
    confirm = page.select_one('#audioImportConfirm')

    assert tab.get_text(strip=True) == "批量导入"
    assert excel["accept"] == ".xls"
    assert audio["accept"] == ".wav,audio/wav"
    assert audio.has_attr("multiple")
    assert confirm.has_attr("disabled")
    assert page.select_one("#audioImportPreview") is not None
