"""Covers cart -> order business logic: totals, stock decrement, and the
guardrails that stop an order being placed in an inconsistent state
(empty cart, insufficient stock)."""


def _first_product_id(client):
    products = client.get("/products").json()
    assert len(products) > 0
    return products[0]["id"], products[0]


def test_add_to_cart_and_totals(client, auth_headers):
    product_id, product = _first_product_id(client)

    client.post("/cart", json={"product_id": product_id, "quantity": 2}, headers=auth_headers)
    resp = client.get("/cart", headers=auth_headers)
    body = resp.json()

    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    assert body["total_amount"] == round(product["price"] * 2, 2)


def test_adding_same_product_twice_increments_quantity(client, auth_headers):
    product_id, _ = _first_product_id(client)

    client.post("/cart", json={"product_id": product_id, "quantity": 1}, headers=auth_headers)
    client.post("/cart", json={"product_id": product_id, "quantity": 2}, headers=auth_headers)

    body = client.get("/cart", headers=auth_headers).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 3


def test_checkout_decrements_stock_and_clears_cart(client, auth_headers):
    product_id, product = _first_product_id(client)
    starting_stock = product["stock"]

    client.post("/cart", json={"product_id": product_id, "quantity": 2}, headers=auth_headers)
    order_resp = client.post("/orders", headers=auth_headers)
    assert order_resp.status_code == 201
    order = order_resp.json()
    assert order["items"][0]["quantity"] == 2

    cart_after = client.get("/cart", headers=auth_headers).json()
    assert cart_after["items"] == []

    product_after = client.get(f"/products/{product_id}").json()
    assert product_after["stock"] == starting_stock - 2

    history = client.get("/orders", headers=auth_headers).json()
    assert len(history) == 1
    assert history[0]["id"] == order["id"]


def test_checkout_with_empty_cart_is_rejected(client, auth_headers):
    resp = client.post("/orders", headers=auth_headers)
    assert resp.status_code == 400


def test_checkout_fails_when_stock_is_insufficient(client, auth_headers):
    product_id, product = _first_product_id(client)

    client.post(
        "/cart",
        json={"product_id": product_id, "quantity": product["stock"] + 1},
        headers=auth_headers,
    )
    resp = client.post("/orders", headers=auth_headers)
    assert resp.status_code == 400

    # Cart and stock must be untouched after a failed checkout.
    cart_after = client.get("/cart", headers=auth_headers).json()
    assert len(cart_after["items"]) == 1
    product_after = client.get(f"/products/{product_id}").json()
    assert product_after["stock"] == product["stock"]
