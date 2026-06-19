import unittest

from agentcanvas.core import (
    CallFact,
    Confidence,
    DatabaseFact,
    DecisionFact,
    EventFact,
    ExternalServiceFact,
    FileFact,
    Provenance,
    RepoFacts,
    RouteFact,
    SourceLocation,
    SymbolFact,
    all_fact_ids,
    repo_facts_to_canvas_model,
    validate_canvas_model,
    validate_repo_facts,
)


class CoreModelTests(unittest.TestCase):
    maxDiff = None

    def test_checkout_flow_maps_to_canvas_journey_with_else_if_and_provenance(self):
        route_source = Provenance(
            extractor="sample-checkout-indexer",
            location=SourceLocation("src/routes/checkout.js", line=7, end_line=38),
            evidence="router.post('/checkout', submitOrder)",
            confidence=Confidence(0.94, "matched route handler call"),
        )
        decision_source = Provenance(
            extractor="sample-checkout-indexer",
            location=SourceLocation("./src/actions/submit-order.js", line=12, end_line=26),
            evidence="if (...) / else if (...) / else",
            confidence=Confidence(0.9, "parsed conditional chain"),
        )

        route_file = FileFact(
            id="file:routes-checkout",
            path="./src/routes/checkout.js",
            language="javascript",
            role="route",
            provenance=(route_source,),
        )
        action_file = FileFact(
            id="file:actions-submit-order",
            path="src/actions/submit-order.js",
            language="javascript",
            role="action",
            provenance=(decision_source,),
        )
        handler = SymbolFact(
            id="symbol:submit-order",
            name="submitOrder",
            qualified_name="checkout.submitOrder",
            symbol_type="function",
            file_id=action_file.id,
            location=SourceLocation("src/actions/submit-order.js", line=5),
            provenance=(decision_source,),
        )
        route = RouteFact(
            id="route:post-checkout",
            path="/checkout",
            methods=("post",),
            file_id=route_file.id,
            handler_symbol_id=handler.id,
            framework="express",
            provenance=(route_source,),
        )
        return_empty = CallFact(
            id="call:return-empty-cart",
            caller_symbol_id=handler.id,
            target_name="returnEmptyCart",
            file_id=action_file.id,
            provenance=(decision_source,),
        )
        inventory_call = CallFact(
            id="call:reserve-inventory",
            caller_symbol_id=handler.id,
            target_name="inventory.reserve",
            file_id=action_file.id,
            condition="inventory.available",
            provenance=(decision_source,),
        )
        stripe = ExternalServiceFact(
            id="service:stripe",
            name="Stripe",
            service_type="payment",
            endpoint="https://api.stripe.com",
            provenance=(decision_source,),
        )
        payment_call = CallFact(
            id="call:authorize-payment",
            caller_symbol_id=handler.id,
            target_name="stripe.paymentIntents.create",
            file_id=action_file.id,
            external_service_id=stripe.id,
            provenance=(decision_source,),
        )
        order_insert = DatabaseFact(
            id="db:insert-order",
            operation="insert",
            entity="orders",
            file_id=action_file.id,
            symbol_id=handler.id,
            provenance=(decision_source,),
        )
        completed_event = EventFact(
            id="event:checkout-completed",
            name="checkout.completed",
            event_type="emit",
            file_id=action_file.id,
            symbol_id=handler.id,
            provenance=(decision_source,),
        )

        repo = RepoFacts(
            workspace={"name": "sample checkout"},
            files=(route_file, action_file),
            symbols=(handler,),
            routes=(route,),
            calls=(return_empty, inventory_call, payment_call),
            events=(completed_event,),
            databases=(order_insert,),
            external_services=(stripe,),
            decisions=(
                DecisionFact(
                    id="decision:empty-cart",
                    owner_symbol_id=handler.id,
                    group_id="checkout-outcome",
                    branch="If",
                    condition="cart.items.length === 0",
                    order=1,
                    file_id=action_file.id,
                    then_refs=(return_empty.id,),
                    provenance=(decision_source,),
                ),
                DecisionFact(
                    id="decision:inventory-unavailable",
                    owner_symbol_id=handler.id,
                    group_id="checkout-outcome",
                    branch="ElseIf",
                    condition="!inventory.available",
                    order=2,
                    file_id=action_file.id,
                    then_refs=(inventory_call.id,),
                    provenance=(decision_source,),
                ),
                DecisionFact(
                    id="decision:checkout-happy-path",
                    owner_symbol_id=handler.id,
                    group_id="checkout-outcome",
                    branch="Else",
                    order=3,
                    file_id=action_file.id,
                    then_refs=(payment_call.id, order_insert.id, completed_event.id),
                    provenance=(decision_source,),
                ),
            ),
        )

        self.assertEqual([], validate_repo_facts(repo))

        canvas = repo_facts_to_canvas_model(repo)
        self.assertEqual([], validate_canvas_model(canvas, known_fact_ids=all_fact_ids(repo)))

        journey = canvas.to_dict()["journeys"][0]
        self.assertEqual("POST /checkout", journey["title"])
        self.assertEqual(
            ["When", "Do", "If", "ElseIf", "Else"],
            [step["kind"] for step in journey["steps"]],
        )

        when_step, _, if_step, elseif_step, else_step = journey["steps"]
        self.assertEqual("src/routes/checkout.js", when_step["provenance"][0]["location"]["path"])
        self.assertEqual("!inventory.available", elseif_step["condition"])
        self.assertEqual(
            "src/actions/submit-order.js",
            elseif_step["provenance"][0]["location"]["path"],
        )
        self.assertEqual(["Call inventory.reserve"], [step["text"] for step in elseif_step["steps"]])
        self.assertEqual(
            ["Call Stripe", "Insert orders", "Emit checkout.completed"],
            [step["text"] for step in else_step["steps"]],
        )
        self.assertEqual(["Call returnEmptyCart"], [step["text"] for step in if_step["steps"]])

        dict_repo = repo.to_dict()
        dict_repo["decisions"][1]["branch"] = "elif"
        dict_canvas = repo_facts_to_canvas_model(dict_repo).to_dict()
        self.assertEqual("ElseIf", dict_canvas["journeys"][0]["steps"][3]["kind"])


if __name__ == "__main__":
    unittest.main()
