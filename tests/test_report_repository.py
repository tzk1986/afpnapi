"""report_repository.collect_report_artifacts 单元测试."""

from pathlib import Path

import pytest

from postman_api_tester.report_repository import (
    collect_report_artifacts,
    configure_report_repository,
)


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    rd = tmp_path / "reports"
    rd.mkdir()
    configure_report_repository(rd)
    return rd


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestResolveArtifactDir:
    """通过 collect_report_artifacts 间接验证 _resolve_artifact_dir。"""

    def test_legacy_report_in_subdirectory(self, reports_dir: Path):
        """legacy 报告在子目录中，通过 source_file 定位正确目录。"""
        sub = reports_dir / "支付公开接口"
        sub.mkdir()
        html = _write(sub / "postman_report.html")

        report = {
            "report_name": "postman_report.html",
            "meta_file": "",
            "details_file": "",
            "source_file": str(html),
        }

        artifacts = collect_report_artifacts(report)
        artifact_names = [a.name for a in artifacts]
        assert "postman_report.html" in artifact_names
        assert all(a.exists() for a in artifacts)

    def test_non_legacy_report_in_subdirectory(self, reports_dir: Path):
        """非 legacy 报告在子目录中，通过 meta_file 定位正确目录。"""
        sub = reports_dir / "子目录"
        sub.mkdir()
        html = _write(sub / "my_report.html")
        meta = _write(sub / "my_report_meta.json")
        details = _write(sub / "my_report_details.json")

        report = {
            "report_name": "my_report.html",
            "meta_file": "子目录/my_report_meta.json",
            "details_file": "子目录/my_report_details.json",
            "source_file": "",
        }

        artifacts = collect_report_artifacts(report)
        artifact_names = [a.name for a in artifacts]
        assert "my_report.html" in artifact_names
        assert "my_report_meta.json" in artifact_names
        assert "my_report_details.json" in artifact_names

    def test_root_level_report(self, reports_dir: Path):
        """根目录下的报告正常工作。"""
        html = _write(reports_dir / "root_report.html")
        meta = _write(reports_dir / "root_report_meta.json")

        report = {
            "report_name": "root_report.html",
            "meta_file": "root_report_meta.json",
            "details_file": "",
            "source_file": "",
        }

        artifacts = collect_report_artifacts(report)
        artifact_names = [a.name for a in artifacts]
        assert "root_report.html" in artifact_names
        assert "root_report_meta.json" in artifact_names

    def test_page_files_in_subdirectory(self, reports_dir: Path):
        """分页文件在子目录中正确收集。"""
        sub = reports_dir / "分页子目录"
        sub.mkdir()
        html = _write(sub / "big_report.html")
        _write(sub / "big_report_page_1.html")
        _write(sub / "big_report_page_2.html")

        report = {
            "report_name": "big_report.html",
            "meta_file": "",
            "details_file": "",
            "source_file": str(html),
        }

        artifacts = collect_report_artifacts(report)
        artifact_names = sorted(a.name for a in artifacts)
        assert "big_report.html" in artifact_names
        assert "big_report_page_1.html" in artifact_names
        assert "big_report_page_2.html" in artifact_names

    def test_page_files_in_root(self, reports_dir: Path):
        """根目录下的分页文件正确收集。"""
        _write(reports_dir / "root_report.html")
        _write(reports_dir / "root_report_page_1.html")
        _write(reports_dir / "root_report_page_2.html")

        report = {
            "report_name": "root_report.html",
            "meta_file": "root_report_meta.json",
            "details_file": "",
            "source_file": "",
        }

        artifacts = collect_report_artifacts(report)
        artifact_names = sorted(a.name for a in artifacts)
        assert "root_report_page_1.html" in artifact_names
        assert "root_report_page_2.html" in artifact_names

    def test_no_duplicates(self, reports_dir: Path):
        """同一文件不会被重复收集。"""
        sub = reports_dir / "去重测试"
        sub.mkdir()
        html = _write(sub / "dup_report.html")

        report = {
            "report_name": "dup_report.html",
            "meta_file": "",
            "details_file": "",
            "source_file": str(html),
        }

        artifacts = collect_report_artifacts(report)
        assert len(artifacts) == len(set(str(a) for a in artifacts))

    def test_empty_report_name(self, reports_dir: Path):
        """report_name 为空时不崩溃。"""
        report = {
            "report_name": "",
            "meta_file": "",
            "details_file": "",
            "source_file": "",
        }

        artifacts = collect_report_artifacts(report)
        assert artifacts == []

    def test_source_file_outside_reports_dir_ignored(self, reports_dir: Path, tmp_path: Path):
        """source_file 在 reports 目录外时被忽略，回退到根目录。"""
        outside = tmp_path / "outside" / "report.html"
        _write(outside)

        report = {
            "report_name": "orphan.html",
            "meta_file": "",
            "details_file": "",
            "source_file": str(outside),
        }

        artifacts = collect_report_artifacts(report)
        for a in artifacts:
            try:
                a.relative_to(reports_dir)
            except ValueError:
                pytest.fail("artifact outside reports_dir")
