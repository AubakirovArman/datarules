ANALYSIS_ONLY_MODE = "analysis_only"


def is_analysis_only(target_mode: str | None, target_table: str | None = None) -> bool:
    return target_mode == ANALYSIS_ONLY_MODE or target_table == ANALYSIS_ONLY_MODE
