import json
import networkx as nx


def build_graph(meeting_id: int, tasks: list, decisions: list, people: list) -> dict:
    """
    Build a directed graph connecting people → tasks → deadlines
    and return it as a node-link dict for the frontend to render.
    """
    G = nx.DiGraph()

    # add meeting node
    G.add_node(f"meeting_{meeting_id}", label=f"Meeting {meeting_id}", type="meeting")

    for person in people:
        G.add_node(person, label=person, type="person")
        G.add_edge(f"meeting_{meeting_id}", person, relation="participant")

    for t in tasks:
        task_id  = f"task_{meeting_id}_{tasks.index(t)}"
        task_lbl = t.get("task", "Unknown task")[:60]
        owner    = t.get("owner", "")
        deadline = t.get("deadline", "")

        G.add_node(task_id, label=task_lbl, type="task")

        if owner and owner in G.nodes:
            G.add_edge(owner, task_id, relation="assigned")
        elif owner:
            G.add_node(owner, label=owner, type="person")
            G.add_edge(owner, task_id, relation="assigned")

        if deadline:
            dl_id = f"deadline_{task_id}"
            G.add_node(dl_id, label=deadline, type="deadline")
            G.add_edge(task_id, dl_id, relation="due_by")

    for i, d in enumerate(decisions):
        dec_id = f"decision_{meeting_id}_{i}"
        G.add_node(dec_id, label=d[:60], type="decision")
        G.add_edge(f"meeting_{meeting_id}", dec_id, relation="decided")

    return nx.node_link_data(G)


def graph_to_json(graph_data: dict) -> str:
    return json.dumps(graph_data)
