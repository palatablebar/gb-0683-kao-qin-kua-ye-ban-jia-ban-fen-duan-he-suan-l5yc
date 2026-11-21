"""月度发布模块对外服务入口（与 handler 内联调用保持同一实现）。"""


def execute(state):  # 月度管线不接入 m1-m7 的单文件 workflow，占位保持模块结构一致
    return state
