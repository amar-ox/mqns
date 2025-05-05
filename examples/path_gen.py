def compute_distances_distribution(end_to_end_distance, number_of_routers, distance_proportion):
    total_segments = number_of_routers + 1  # Links = routers + 1

    if number_of_routers == 0:
        return [end_to_end_distance]  # No routers = single segment

    if distance_proportion == "uniform":
        segment_length = end_to_end_distance // total_segments
        return [segment_length] * total_segments

    elif distance_proportion == "increasing":
        # Quadratic-like increase from left to right
        weights = [2 * i + 1 for i in range(total_segments)]
        total_weight = sum(weights)
        distances = [int(end_to_end_distance * (w / total_weight)) for w in weights]
        return distances

    elif distance_proportion == "decreasing":
        # Quadratic-like decrease from left to right
        weights = [2 * i + 1 for i in range(total_segments)][::-1]
        total_weight = sum(weights)
        distances = [int(end_to_end_distance * (w / total_weight)) for w in weights]
        return distances

    elif distance_proportion == "mid_bottleneck":
        # Middle segment(s) are 1.2x longer than others
        if total_segments <= 2:
            return [end_to_end_distance // total_segments] * total_segments

        is_even = total_segments % 2 == 0
        num_middle = 2 if is_even else 1
        num_edges = total_segments - num_middle

        # Base edge segment length, solving for: base * num_edges + 1.2 * base * num_middle = total
        base_edge_distance = int(end_to_end_distance / (num_edges + 1.2 * num_middle))
        middle_distance = int(base_edge_distance * 1.2)

        result = [base_edge_distance] * (num_edges // 2)
        result += [middle_distance] * num_middle
        result += [base_edge_distance] * (num_edges // 2)
        return result

    else:
        raise ValueError(f"Invalid distance proportion type: {distance_proportion}")

def compute_distances_distribution_abd(end_to_end_distance, number_of_routers, distance_proportion):
    total_segments = number_of_routers + 1  # Source, routers, destination
    # Handle cases with no routers or just one router
    if number_of_routers == 0:
        return [end_to_end_distance]  # Entire distance as a single segment
    if distance_proportion == "uniform":
        return [end_to_end_distance // total_segments] * total_segments
    elif distance_proportion == "increasing":
        weights = [i*2+ 1 for i in range(total_segments)]
        total_weight = sum(weights)
        distances = [end_to_end_distance * (w / total_weight) for w in weights]
        return [int(d) for d in distances]
    elif distance_proportion == "decreasing":
        weights = [i*2+ 1 for i in range(total_segments)][::-1]
        total_weight = sum(weights)
        distances = [end_to_end_distance * (w / total_weight) for w in weights]
        return [int(d) for d in distances]
    if distance_proportion == "mid_bottleneck":
        # Compute base distance for edge segments
        edge_segments = total_segments - 2 if total_segments % 2 == 0 else total_segments - 1
        base_edge_distance = int(end_to_end_distance / (1.2 * edge_segments + (2 if total_segments % 2 == 0 else 1)))
        # Compute middle distances
        if total_segments % 2 == 0:  # Even segments: two middle segments
            middle_distance = int(base_edge_distance * 1.2)
            return [base_edge_distance] * (edge_segments // 2) + [middle_distance, middle_distance] + [base_edge_distance] * (edge_segments // 2)
        else:  # Odd segments: single middle segment
            middle_distance = int(base_edge_distance * 1.2)
            return [base_edge_distance] * (edge_segments // 2) + [middle_distance] + [base_edge_distance] * (edge_segments // 2)
    else:
        raise ValueError(f"Invalid distance proportion type: {distance_proportion}")

# Example usage:
if __name__ == "__main__":
    for num_routers in [3,4,5]:
        for prop in ["uniform", "increasing", "decreasing", "mid_bottleneck"]:
            print(f"{prop.title()} (150 km, {num_routers} routers): {compute_distances_distribution(150, num_routers, prop)}")
            print(f"{prop.title()} (150 km, {num_routers} routers): {compute_distances_distribution_abd(150, num_routers, prop)}")
