from tasks import add
print("pingng redis.....")
result = add.delay(5, 7)
print("Task queued:", result.id)