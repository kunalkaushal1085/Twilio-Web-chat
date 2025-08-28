def fibonacci_generator(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Memory efficient for large datasets
fib = fibonacci_generator(1000000)
print(fib,'fib')