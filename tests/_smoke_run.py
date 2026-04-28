import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from viewmodel import ViewModel
from commands.task_commands import AddTaskCommand, UpdateTaskCommand, ToggleDoneStatusCommand, DeleteSelectedTasksCommand, RemoveLinkCommand


def print_tasks(vm: ViewModel):
    print("--- tasks snapshot ---")
    for i, t in enumerate(vm.tasks):
        print(i, t.id, t.text, "done=" + str(t.is_done), "children=" + str(len(t.children)))


def run():
    vm = ViewModel()
    vm.set_ui(None)

    # add
    print('Adding tasks...')
    cmd1 = AddTaskCommand(vm, task_text='Task A')
    cmd2 = AddTaskCommand(vm, task_text='Task B')
    vm.execute_command(cmd1)
    vm.execute_command(cmd2)
    print_tasks(vm)

    # update
    tid = vm.tasks[0].id
    print('Updating first task...')
    upd = UpdateTaskCommand(vm, task_id=tid, new_text='Task A edited', new_priority='high')
    vm.execute_command(upd)
    print_tasks(vm)

    # toggle done
    print('Toggling done...')
    tog = ToggleDoneStatusCommand(vm, task_ids=[tid])
    vm.execute_command(tog)
    print_tasks(vm)

    # remove link (no link present) -> should be harmless
    print('Removing link...')
    rl = RemoveLinkCommand(vm, task_id=tid)
    vm.execute_command(rl)
    print_tasks(vm)

    # delete
    print('Deleting tasks...')
    dcmd = DeleteSelectedTasksCommand(vm, task_ids=[tid], confirmed=True)
    vm.execute_command(dcmd)
    print_tasks(vm)


if __name__ == '__main__':
    run()
