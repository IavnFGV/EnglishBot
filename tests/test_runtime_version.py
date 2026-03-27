from englishbot.runtime_version import RuntimeVersionInfo, get_runtime_version_info


def test_get_runtime_version_info_reads_git_metadata_from_environment() -> None:
    info = get_runtime_version_info(
        {
            "ENGLISHBOT_BUILD_VERSION": "0.1.0",
            "ENGLISHBOT_BUILD_NUMBER": "3",
            "ENGLISHBOT_GIT_SHA": "abc1234",
            "ENGLISHBOT_GIT_BRANCH": "main",
        }
    )

    assert info.package_version == "0.1.0"
    assert info.build_number == "3"
    assert info.git_sha == "abc1234"
    assert info.git_branch == "main"


def test_get_runtime_version_info_normalizes_blank_git_metadata() -> None:
    info = get_runtime_version_info(
        {
            "ENGLISHBOT_BUILD_VERSION": "   ",
            "ENGLISHBOT_BUILD_NUMBER": "",
            "ENGLISHBOT_GIT_SHA": "   ",
            "ENGLISHBOT_GIT_BRANCH": "",
        }
    )

    assert isinstance(info, RuntimeVersionInfo)
    assert info.package_version
    assert info.build_number is None
    assert info.git_sha is None
    assert info.git_branch is None
