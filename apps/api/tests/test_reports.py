"""Editable report document API tests."""

from io import BytesIO
from urllib.parse import quote
from uuid import uuid4

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import reports as reports_api
from app.db.tables import (
    AnalysisRun,
    ArtifactRecord,
    Project,
    ReportBlock,
    ReportDocument,
    ReportPage,
)


async def _seed_analysis(
    db_session: AsyncSession,
    project: Project,
) -> tuple[AnalysisRun, ArtifactRecord]:
    run = AnalysisRun(
        project_id=project.id,
        query="概览本月经营表现",
        state="completed",
        stage="completed",
        report={"summary": "本月收入增长"},
    )
    db_session.add(run)
    await db_session.flush()
    artifact = ArtifactRecord(
        project_id=project.id,
        analysis_run_id=run.id,
        kind="chart",
        title="月度收入趋势",
        payload={"series": [100, 120, 140]},
        technical_details={"query_hash": "immutable"},
    )
    db_session.add(artifact)
    await db_session.commit()
    return run, artifact


@pytest.mark.asyncio
async def test_create_list_and_get_report_with_manual_and_artifact_blocks(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="经营驾驶舱")
    db_session.add(project)
    await db_session.flush()
    run, artifact = await _seed_analysis(db_session, project)

    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "七月经营报告",
            "description": "人工叙事与已验证调查结果的组合",
            "pages": [
                {
                    "title": "概览",
                    "order_index": 0,
                    "config": {"columns": 12},
                    "blocks": [
                        {
                            "block_type": "text",
                            "title": "管理摘要",
                            "order_index": 0,
                            "source_kind": "manual",
                            "content": {"text": "这里可以自由编辑。"},
                            "layout": {"x": 0, "y": 0, "w": 12, "h": 3},
                        },
                        {
                            "block_type": "chart",
                            "title": "收入趋势",
                            "order_index": 1,
                            "source_kind": "artifact",
                            "artifact_id": str(artifact.id),
                            "content": {"caption": "来自已完成调查"},
                            "layout": {"x": 0, "y": 3, "w": 8, "h": 6},
                            "config": {"chart_type": "line"},
                        },
                    ],
                }
            ],
        },
    )

    assert created.status_code == 201, created.text
    document = created.json()["data"]
    assert document["version"] == 1
    assert document["pages"][0]["config"] == {"columns": 12}
    assert [block["source_kind"] for block in document["pages"][0]["blocks"]] == [
        "manual",
        "artifact",
    ]
    artifact_block = document["pages"][0]["blocks"][1]
    assert artifact_block["artifact_id"] == str(artifact.id)
    assert artifact_block["analysis_run_id"] == str(run.id)
    assert artifact_block["source_available"] is True
    assert artifact_block["source_ref"]["artifact_id"] == str(artifact.id)
    assert artifact_block["source_ref"]["snapshot"]["payload"] == {
        "series": [100, 120, 140]
    }

    listing = await client.get(f"/api/v1/projects/{project.id}/reports")
    assert listing.status_code == 200
    assert listing.json()["data"] == [
        {
            "id": document["id"],
            "project_id": str(project.id),
            "title": "七月经营报告",
            "description": "人工叙事与已验证调查结果的组合",
            "status": "draft",
            "version": 1,
            "page_count": 1,
            "block_count": 2,
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
        }
    ]

    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{document['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["data"] == document
    stored_artifact = await db_session.get(ArtifactRecord, artifact.id)
    assert stored_artifact is not None
    assert stored_artifact.payload == {"series": [100, 120, 140]}
    assert stored_artifact.technical_details == {"query_hash": "immutable"}


@pytest.mark.asyncio
async def test_full_document_update_upserts_pages_and_blocks_with_version_guard(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="可编辑报表")
    db_session.add(project)
    await db_session.commit()
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "初稿",
            "pages": [
                {
                    "title": "概览",
                    "blocks": [
                        {
                            "block_type": "text",
                            "source_kind": "manual",
                            "content": {"text": "旧内容"},
                            "layout": {"x": 0, "y": 0, "w": 6, "h": 2},
                        }
                    ],
                }
            ],
        },
    )
    initial = created.json()["data"]
    page = initial["pages"][0]
    block = page["blocks"][0]

    updated = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{initial['id']}",
        json={
            "expected_version": 1,
            "title": "正式经营报告",
            "pages": [
                {
                    "id": page["id"],
                    "title": "经营概览",
                    "order_index": 0,
                    "config": {"background": "paper"},
                    "blocks": [
                        {
                            "id": block["id"],
                            "block_type": "text",
                            "title": "结论",
                            "order_index": 1,
                            "source_kind": "manual",
                            "content": {"text": "用户修改后的内容"},
                            "layout": {"x": 0, "y": 0, "w": 12, "h": 2},
                            "config": {"tone": "plain"},
                        },
                        {
                            "block_type": "metric",
                            "title": "手工目标",
                            "order_index": 0,
                            "source_kind": "manual",
                            "content": {"value": 180, "unit": "万元"},
                            "layout": {"x": 0, "y": 2, "w": 3, "h": 2},
                        },
                    ],
                },
                {
                    "title": "明细",
                    "order_index": 1,
                    "blocks": [],
                },
            ],
        },
    )

    assert updated.status_code == 200, updated.text
    document = updated.json()["data"]
    assert document["title"] == "正式经营报告"
    assert document["version"] == 2
    assert [page["title"] for page in document["pages"]] == ["经营概览", "明细"]
    assert document["pages"][0]["version"] == 2
    assert document["pages"][0]["blocks"][1]["id"] == block["id"]
    assert document["pages"][0]["blocks"][1]["version"] == 2
    assert document["pages"][0]["blocks"][1]["content"] == {
        "text": "用户修改后的内容"
    }

    # Bypass the in-memory fast-fail: the database CAS must still reject the
    # second writer that presents the same expected version.
    monkeypatch.setattr(reports_api, "_assert_expected_version", lambda *_args: None)
    stale = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{initial['id']}",
        json={"expected_version": 1, "title": "过期覆盖"},
    )
    assert stale.status_code == 409
    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{initial['id']}"
    )
    assert detail.json()["data"]["title"] == "正式经营报告"


@pytest.mark.asyncio
async def test_report_source_references_are_project_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
):
    report_project = Project(name="报表项目")
    foreign_project = Project(name="其他项目")
    db_session.add_all([report_project, foreign_project])
    await db_session.flush()
    _, foreign_artifact = await _seed_analysis(db_session, foreign_project)

    rejected = await client.post(
        f"/api/v1/projects/{report_project.id}/reports",
        json={
            "title": "不能跨项目引用",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "chart",
                            "source_kind": "artifact",
                            "artifact_id": str(foreign_artifact.id),
                        }
                    ]
                }
            ],
        },
    )

    assert rejected.status_code == 400
    assert "不属于当前项目" in rejected.json()["detail"]
    report_count = await db_session.scalar(select(func.count(ReportDocument.id)))
    assert report_count == 0


@pytest.mark.asyncio
async def test_delete_report_cascades_editable_tree_but_keeps_analysis_artifact(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="报表删除边界")
    db_session.add(project)
    await db_session.flush()
    run, artifact = await _seed_analysis(db_session, project)
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "待删除报表",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "chart",
                            "source_kind": "artifact",
                            "artifact_id": str(artifact.id),
                        }
                    ]
                }
            ],
        },
    )
    report_id = created.json()["data"]["id"]

    deleted = await client.delete(
        f"/api/v1/projects/{project.id}/reports/{report_id}"
    )

    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"id": report_id, "deleted": True}
    assert await db_session.scalar(select(func.count(ReportDocument.id))) == 0
    assert await db_session.scalar(select(func.count(ReportPage.id))) == 0
    assert await db_session.scalar(select(func.count(ReportBlock.id))) == 0
    assert await db_session.get(AnalysisRun, run.id) is not None
    assert await db_session.get(ArtifactRecord, artifact.id) is not None


@pytest.mark.asyncio
async def test_block_crud_keeps_manual_source_explicit(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="区块编辑")
    db_session.add(project)
    await db_session.commit()
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={"title": "区块编辑测试"},
    )
    report = created.json()["data"]
    page = report["pages"][0]

    added = await client.post(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks",
        json={
            "block_type": "text",
            "source_kind": "manual",
            "content": {"text": "用户输入"},
        },
    )
    assert added.status_code == 201
    block = added.json()["data"]["pages"][0]["blocks"][0]
    assert block["source_kind"] == "manual"
    assert block["version"] == 1

    edited = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks/{block['id']}",
        json={
            "expected_version": 1,
            "title": "手工备注",
            "content": {"text": "可以继续编辑"},
            "layout": {"x": 3, "y": 1, "w": 6, "h": 2},
        },
    )
    assert edited.status_code == 200
    edited_block = edited.json()["data"]["pages"][0]["blocks"][0]
    assert edited_block["title"] == "手工备注"
    assert edited_block["version"] == 2
    assert edited_block["source_kind"] == "manual"

    removed = await client.delete(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks/{block['id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["pages"][0]["blocks"] == []


@pytest.mark.asyncio
async def test_patch_rejects_null_for_non_nullable_report_fields(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="拒绝空值")
    db_session.add(project)
    await db_session.commit()
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "保持有效",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "text",
                            "source_kind": "manual",
                            "content": {"text": "不会被空值覆盖"},
                        }
                    ]
                }
            ],
        },
    )
    report = created.json()["data"]
    page = report["pages"][0]
    block = page["blocks"][0]

    invalid_report = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}",
        json={"expected_version": report["version"], "title": None},
    )
    invalid_page = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}",
        json={"expected_version": page["version"], "config": None},
    )
    invalid_block = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks/{block['id']}",
        json={"expected_version": block["version"], "content": None},
    )

    assert invalid_report.status_code == 422
    assert invalid_page.status_code == 422
    assert invalid_block.status_code == 422
    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{report['id']}"
    )
    assert detail.json()["data"]["title"] == "保持有效"
    assert detail.json()["data"]["pages"][0]["config"] == {}
    assert detail.json()["data"]["pages"][0]["blocks"][0]["content"] == {
        "text": "不会被空值覆盖"
    }


@pytest.mark.asyncio
async def test_page_and_block_patch_use_database_compare_and_swap(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="并发编辑")
    db_session.add(project)
    await db_session.commit()
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "并发保护",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "text",
                            "source_kind": "manual",
                            "content": {"text": "原始内容"},
                        }
                    ]
                }
            ],
        },
    )
    report = created.json()["data"]
    page = report["pages"][0]
    block = page["blocks"][0]

    first_page_write = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}",
        json={"expected_version": page["version"], "title": "第一个写入者"},
    )
    assert first_page_write.status_code == 200

    # Ignore the in-memory precheck; UPDATE ... WHERE id/version must be the
    # layer that rejects a second writer with the same version.
    monkeypatch.setattr(reports_api, "_assert_expected_version", lambda *_args: None)
    stale_page_write = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}",
        json={"expected_version": page["version"], "title": "第二个写入者"},
    )
    assert stale_page_write.status_code == 409

    first_block_write = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks/{block['id']}",
        json={
            "expected_version": block["version"],
            "content": {"text": "第一个区块写入者"},
        },
    )
    assert first_block_write.status_code == 200
    stale_block_write = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{report['id']}/pages/{page['id']}/blocks/{block['id']}",
        json={
            "expected_version": block["version"],
            "content": {"text": "第二个区块写入者"},
        },
    )
    assert stale_block_write.status_code == 409

    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{report['id']}"
    )
    current = detail.json()["data"]
    assert current["pages"][0]["title"] == "第一个写入者"
    assert current["pages"][0]["blocks"][0]["content"] == {
        "text": "第一个区块写入者"
    }


@pytest.mark.asyncio
async def test_source_snapshot_survives_analysis_cleanup_and_remains_editable(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    await db_session.commit()
    project = Project(name="来源保留")
    db_session.add(project)
    await db_session.flush()
    run, artifact = await _seed_analysis(db_session, project)
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "独立于调查历史的报表",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "chart",
                            "source_kind": "artifact",
                            "artifact_id": str(artifact.id),
                            "content": {"caption": "已经固定到报表的静态说明"},
                        }
                    ]
                }
            ],
        },
    )
    document = created.json()["data"]
    original_block = document["pages"][0]["blocks"][0]
    original_ref = original_block["source_ref"]

    # This is the same cleanup boundary used when an investigation is removed:
    # artifacts cascade away and live report FKs become NULL, while the report
    # itself must remain readable.
    await db_session.execute(delete(AnalysisRun).where(AnalysisRun.id == run.id))
    await db_session.commit()

    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{document['id']}"
    )
    detached = detail.json()["data"]
    detached_page = detached["pages"][0]
    detached_block = detached_page["blocks"][0]
    assert detached_block["analysis_run_id"] is None
    assert detached_block["artifact_id"] is None
    assert detached_block["source_available"] is False
    assert detached_block["source_ref"] == original_ref
    assert detached_block["source_ref"]["artifact_id"] == str(artifact.id)
    assert detached_block["source_ref"]["snapshot"]["payload"] == {
        "series": [100, 120, 140]
    }
    assert detached_block["content"] == {
        "caption": "已经固定到报表的静态说明"
    }

    edited = await client.patch(
        f"/api/v1/projects/{project.id}/reports/{document['id']}",
        json={
            "expected_version": detached["version"],
            "pages": [
                {
                    "id": detached_page["id"],
                    "title": detached_page["title"],
                    "order_index": detached_page["order_index"],
                    "config": detached_page["config"],
                    "blocks": [
                        {
                            "id": detached_block["id"],
                            "block_type": detached_block["block_type"],
                            "title": detached_block["title"],
                            "order_index": detached_block["order_index"],
                            "source_kind": detached_block["source_kind"],
                            "analysis_run_id": None,
                            "artifact_id": None,
                            "source_ref": detached_block["source_ref"],
                            "content": {"caption": "来源已清理，但内容仍可编辑"},
                            "layout": detached_block["layout"],
                            "config": detached_block["config"],
                        }
                    ],
                }
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    edited_block = edited.json()["data"]["pages"][0]["blocks"][0]
    assert edited_block["source_available"] is False
    assert edited_block["source_ref"] == original_ref
    assert edited_block["content"] == {"caption": "来源已清理，但内容仍可编辑"}


@pytest.mark.asyncio
async def test_unknown_block_type_is_rejected_before_persistence(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="区块类型契约")
    db_session.add(project)
    await db_session.commit()

    rejected = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": "不可渲染区块",
            "pages": [
                {
                    "blocks": [
                        {
                            "block_type": "narrative",
                            "source_kind": "manual",
                        }
                    ]
                }
            ],
        },
    )

    assert rejected.status_code == 422
    assert await db_session.scalar(select(func.count(ReportDocument.id))) == 0


def test_report_source_kind_requires_explicit_provenance() -> None:
    # FastAPI/Pydantic handles malformed provenance before touching the database.
    from app.models.reports import ReportBlockCreate

    with pytest.raises(ValueError):
        ReportBlockCreate(block_type="text", source_kind="manual", analysis_run_id=uuid4())


@pytest.mark.asyncio
async def test_export_report_xlsx_is_safe_and_contains_structured_business_data(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="Excel 导出")
    db_session.add(project)
    await db_session.commit()
    title = "七月经营/报告"
    created = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        json={
            "title": title,
            "description": "供经营复盘使用",
            "pages": [
                {
                    "title": "概览",
                    "blocks": [
                        {
                            "block_type": "chart",
                            "title": "趋势/明细",
                            "order_index": 0,
                            "source_kind": "manual",
                            "content": {
                                "data": [
                                    {
                                        "月份": "=1+1",
                                        "收入": 120.5,
                                        "sql": "SELECT secret",
                                        "python": "open('/tmp/secret')",
                                        "technical_details": {"token": "secret"},
                                    },
                                    {
                                        "月份": "七月",
                                        "收入": 140,
                                        "备注": {
                                            "状态": "已确认",
                                            "sql": "SELECT nested_secret",
                                            "详情": {"python": "nested_secret()"},
                                        },
                                    },
                                ],
                                "sql": "SELECT sibling_secret",
                                "python": "print('sibling_secret')",
                                "technical_details": {"tool_history": ["secret"]},
                            },
                        },
                        {
                            "block_type": "table",
                            "title": "趋势/明细",
                            "order_index": 1,
                            "source_kind": "manual",
                            "content": {"rows": [{"门店": "南京", "订单": 12}]},
                        },
                        {
                            "block_type": "chart",
                            "title": "单列值",
                            "order_index": 2,
                            "source_kind": "manual",
                            "content": {"values": ["@SUM(A1:A2)", 2]},
                        },
                        {
                            "block_type": "text",
                            "title": "不应导出为数据页",
                            "order_index": 3,
                            "source_kind": "manual",
                            "content": {"rows": [{"sql": "SELECT hidden"}], "text": "结论"},
                        },
                    ],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/projects/{project.id}/reports/{report_id}/export.xlsx"
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == (
        f"attachment; filename=\"report.xlsx\"; filename*=UTF-8''{quote('七月经营_报告.xlsx', safe='')}"
    )
    workbook = load_workbook(BytesIO(response.content), data_only=False)
    assert workbook.sheetnames == ["报表概览", "趋势 明细", "趋势 明细 (2)", "单列值"]
    assert all(len(name) <= 31 for name in workbook.sheetnames)

    trend = workbook["趋势 明细"]
    assert [cell.value for cell in trend[1]] == ["月份", "收入", "备注"]
    assert trend["A2"].value == "'=1+1"
    assert trend["A2"].data_type == "s"
    assert trend["C3"].value == '{"状态": "已确认", "详情": {}}'
    assert workbook["单列值"]["A2"].value == "'@SUM(A1:A2)"

    all_values = {
        str(cell.value)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    }
    assert "SELECT secret" not in all_values
    assert "SELECT nested_secret" not in all_values
    assert "open('/tmp/secret')" not in all_values
    assert "nested_secret()" not in all_values
    assert "technical_details" not in all_values
