from viewmodel import ViewModel

vm = ViewModel()
vm.tasks, status = vm.task_manager.load_tasks()
print('Before:')
for t in vm.tasks:
    print(t.id, t.text, t.is_done)
    for c in t.children:
        print('  child', c.id, c.text, c.is_done)

# child id from tasks.json
child_id = '78094cbf-e2fe-4b82-b9d6-f081cb37ff38'
# 1) 先把 child 標為已完成（模擬使用者或其它操作）
vm.update_task(child_id, new_is_done=True)
print('\nAfter setting child DONE:')
for t in vm.tasks:
    print(t.id, t.text, t.is_done)
    for c in t.children:
        print('  child', c.id, c.text, c.is_done)

# 2) 再把 child 設回未完成，期望父項也會被標示為未完成
vm.update_task(child_id, new_is_done=False)

print('\nAfter toggling child:')
for t in vm.tasks:
    print(t.id, t.text, t.is_done)
    for c in t.children:
        print('  child', c.id, c.text, c.is_done)
