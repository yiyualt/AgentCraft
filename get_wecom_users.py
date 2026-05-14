"""获取企业微信通讯录成员列表.

用于查看企业微信中的用户账号ID。
"""

import os
from dotenv import load_dotenv
load_dotenv()

from wechatpy.enterprise import WeChatClient


def get_user_list():
    """获取企业微信成员列表."""
    corp_id = os.environ.get("WECOM_CORP_ID")
    secret = os.environ.get("WECOM_SECRET")

    if not corp_id or not secret:
        print("错误: 未配置 WECOM_CORP_ID 或 WECOM_SECRET")
        return

    client = WeChatClient(corp_id=corp_id, secret=secret)

    try:
        # 先获取部门列表
        departments = client.department.list()
        print(f"\n部门列表 (共 {len(departments)} 个):\n")

        dept_ids = []
        for dept in departments:
            dept_id = dept.get("id", 0)
            name = dept.get("name", "")
            dept_ids.append(dept_id)
            print(f"  ID: {dept_id}, 名称: {name}")

        # 获取每个部门的成员
        print(f"\n企业微信成员列表:\n")
        print("-" * 60)
        print(f"{'账号':<15} {'姓名':<10} {'部门':<10}")
        print("-" * 60)

        for dept_id in dept_ids:
            try:
                users = client.user.list(department_id=dept_id)
                dept_name = next(
                    (d.get("name", "") for d in departments if d.get("id") == dept_id),
                    ""
                )

                for user in users:
                    user_id = user.get("userid", "")
                    name = user.get("name", "")
                    print(f"{user_id:<15} {name:<10} {dept_name:<10}")
            except Exception as e:
                print(f"获取部门 {dept_id} 成员失败: {e}")

        print("-" * 60)

    except Exception as e:
        print(f"获取用户列表失败: {e}")
        print("\n提示: 如果失败，可能是因为应用没有通讯录管理权限。")
        print("解决方案:")
        print("1. 在企业微信管理后台，为应用添加'通讯录'权限")
        print("2. 或者直接在管理后台查看用户账号")


if __name__ == "__main__":
    get_user_list()