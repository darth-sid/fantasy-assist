from contracts import ContextBlock


def assemble(blocks: list[ContextBlock]) -> str:
    parts = []
    for block in blocks:
        if block.status == "ok":
            parts.append(block.content)
        elif block.status == "empty":
            label = block.source.upper().replace("_", " ")
            parts.append(f"{label}: no data found")
        else:  # error
            label = block.source.upper().replace("_", " ")
            parts.append(f"{label}: fetch error")
    return "\n\n".join(parts)
