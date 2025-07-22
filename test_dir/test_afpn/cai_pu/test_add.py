import requests
import pandas as pd

# url = "http://10.50.11.120:9301/api/recipe/addRecipe"

# # 固定参数
# payload_template = {
#     "libraryId": "6598bcae1539ff67bd2aefcf8cc63e93",
#     "code": "",  # 待替换
#     "name": "",  # 待替换
#     "categoryId": "4811e4d460427605869acee8dc18369b",
#     "pubFlag": 1,
#     "mealCategoryIdFirst": "920b8dc51058d6d02bbe0b32f9a5409c",
#     "mealCategoryIdSecond": "ad515f677d47946971ff6205f56783ca",
#     "labelIdSet": ["2fc3adf3ae331e00c709a3bf5828392e", "4d3d71c52dc7018c0e7061aabd6bf172"]
# }
# headers = {
#     "content-type": "application/json",
#     "token": "RENDQTMyNUMwMTRBMjY3MkEyQTBBNzVCQjE4OTUxNjQ=.Njc0NjVCNDJCMEEzNzU2MkJDNzJEMzkyQTIwRDA0NTg="
# }

# excel_path = r"D:\tangzk\20250722\菜品新增导入模板20250722001.xlsx"  # 请替换为你的Excel文件路径
# df = pd.read_excel(excel_path)

# for idx, row in df.iterrows():
#     payload = payload_template.copy()
#     payload["code"] = row.get("*菜谱编码", "")
#     payload["name"] = row.get("*菜品名称", "")
#     try:
#         response = requests.post(url, json=payload, headers=headers)
#         print(f"Row {idx}: {response.json()}")
#     except Exception as e:
#         print(f"Row {idx} failed: {e}")


url_spec = "http://10.50.11.120:9301/api/recipe/spec/addSpec"

spec_payload_template =  {
  "recipeId": "",  # 待替换
  "name": "标准",
  "yieldWeight": 2000,
  "yieldPercent": 100,
  "enableFlag": 1,
  "releaseStatus": 3,
  "productionMethod": 1,
  "itemList": [
    {
      "ingredientId": "40cad324f765969b690e7b00218c60e9",
      "weight": 2000
    }
  ]
}
headers = {
  "content-type": "application/json",
  "token": "RENDQTMyNUMwMTRBMjY3MkEyQTBBNzVCQjE4OTUxNjQ=.Njc0NjVCNDJCMEEzNzU2MkJDNzJEMzkyQTIwRDA0NTg="
}

excel_path = r"D:\tangzk\20250722\guige1.xlsx"  # 请替换为你的Excel文件路径
df = pd.read_excel(excel_path)

for idx, row in df.iterrows():
    spec_payload = spec_payload_template.copy()
    spec_payload["recipeId"] = row.get("recipeId", "")
    try:
        response = requests.post(url_spec, json=spec_payload, headers=headers)
        print(f"Row {idx} addSpec: {response.json()}")
    except Exception as e:
        print(f"Row {idx} addSpec failed: {e}")


if __name__ == "__main__":
    pass