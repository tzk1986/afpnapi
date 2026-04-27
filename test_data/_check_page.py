import urllib.request
res = urllib.request.urlopen('http://127.0.0.1:5000/')
html = res.read().decode('utf-8')
print('Status:', res.status)
print('HTML Length:', len(html))
print('collectionFile pos:', html.find('collectionFile'))
print('upload-grid pos:', html.find('upload-grid'))
print('上传并执行 pos:', html.find('上传并执行'))
