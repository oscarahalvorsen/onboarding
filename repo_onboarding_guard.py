import random

def generate_random_list(size=10, low=1, high=100):
    return [random.randint(low, high) for _ in range(size)]


def find_stats(numbers):
    return {
        "min": min(numbers),
        "max": max(numbers),
        "mean": sum(numbers) / len(numbers),
        "sorted": sorted(numbers),
    }

# Example usage
if __name__ == "__main__":
    numbers = generate_random_list()
    print(f"Generated: {numbers}")
    stats = find_stats(numbers)
    for key, value in stats.items():
        print(f"  {key}: {value}")