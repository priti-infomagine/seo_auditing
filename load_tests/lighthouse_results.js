import http from "k6/http";

export const options = {
    scenarios: {
        lighthouse_results: {
            executor: "constant-arrival-rate",
            rate: 1,
            timeUnit: "1s",
            duration: "10s",
            preAllocatedVUs: 2,
            maxVUs: 5,
        },
    },
};

export default function () {
    const url =
        "http://localhost:8000/api/v1/lighthouse/results/4d849afb-4b04-43db-a17e-05b99d5d7464";

    const response = http.get(url);

    console.log(`STATUS=${response.status} BODY=${response.body}`);
}