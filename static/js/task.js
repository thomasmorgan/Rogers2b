/*
 * Requires:
 *     psiturk.js
 *     utils.js
 */

// Initalize psiturk object
var psiTurk = new PsiTurk(uniqueId, adServerLoc, mode);

var mycondition = condition;  // these two variables are passed by the psiturk server process
var mycounterbalance = counterbalance;  // they tell you which condition you have been assigned to
// they are not used in the stroop code but may be useful to you

// All pages to be loaded
var pages = [
    "instructions/instruct-0.html",
    "instructions/instruct-1.html",
    "instructions/instruct-1-5.html",
    "instructions/instruct-2.html",
    "instructions/instruct-3.html",
    "instructions/instruct-test.html",
    "instructions/instruct-ready.html",
    "stage.html",
    "postquestionnaire.html",
    "tampering.html"
];

psiTurk.preloadPages(pages);

var instructionPages = [ // add as a list as many pages as you like
    "instructions/instruct-0.html",
    "instructions/instruct-1.html",
    "instructions/instruct-1-5.html",
    "instructions/instruct-2.html",
    "instructions/instruct-3.html",
    "instructions/instruct-test.html",
    "instructions/instruct-ready.html",
];

var num_practice_trials = 5;


/********************
* HTML manipulation
*
* All HTML files in the templates directory are requested
* from the server when the PsiTurk object is created above. We
* need code to get those pages from the PsiTurk object and
* insert them into the document.
*
********************/

/********************
* STROOP TEST       *
********************/
var StroopExperiment = function() {

    trial = 0;
    lock = true;

    // Kick people out if they change their workerId.
    function ensureSameWorker() {
        workerId = amplify.store("wallace_worker_id");
        workerIdNew = getParameterByName('workerId');

        if (typeof workerId === 'undefined') {
            amplify.store("wallace_worker_id", workerIdNew);
        } else {
            if ((workerIdNew != workerId) && (workerIdNew.substring(0,5) != "debug")) {
                currentview = psiTurk.showPage('tampering.html');
            }
        }
    }

    // Load the stage.html snippet into the body of the page
    psiTurk.showPage('stage.html');
    $("#response-form").hide();
    $("#finish-reading").hide();

    // Create the agent.
    createAgent = function() {

        ensureSameWorker();

        reqwest({
            url: "/node/" + uniqueId,
            method: 'post',
            type: 'json',
            success: function (resp) {
                my_node_id = resp.node.id;
                get_gene(my_node_id);
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                if (err_response.hasOwnProperty('html')) {
                    $('body').html(err_response.html);
                } else {
                    currentview = new Questionnaire();
                }
            }
        });
    };

    // Get all the infos
    get_gene = function(my_node_id) {
        reqwest({
            url: "/node/" + my_node_id + "/infos",
            method: 'get',
            data: { info_type: "LearningGene" },
            type: 'json',
            success: function (resp) {
                learning_strategy = resp.infos[0].contents;
                get_pending_transmissions(my_node_id);
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
    };

    get_pending_transmissions = function(my_node_id) {
        reqwest({
            url: "/node/" + my_node_id + "/transmissions",
            method: 'get',
            data: { direction: "incoming",
                    status: "pending" },
            type: 'json',
            success: function (resp) {
                if (learning_strategy == "asocial") {
                    infos_to_get = [resp.transmissions[0].info_id];
                } else {
                    infos_to_get = [resp.transmissions[0].info_id, resp.transmissions[1].info_id];
                }
                get_first_info(infos_to_get[0]);
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
    };

    get_first_info = function(info_id) {
        reqwest({
            url: "/info/" + my_node_id + "/" + info_id,
            method: 'get',
            type: 'json',
            success: function (resp) {
                if (resp.info.type == "state") {
                    state = resp.info.contents;
                } else {
                    meme = resp.info.contents;
                }
                if (learning_strategy == "social") {
                    get_second_info(infos_to_get[1]);
                } else {
                    presentStimuli();
                }
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
    };

    get_second_info = function(info_id) {
        reqwest({
            url: "/info/" + my_node_id + "/" + info_id,
            method: 'get',
            type: 'json',
            success: function (resp) {
                if (resp.info.type == "state") {
                    state = resp.info.contents;
                } else {
                    meme = resp.info.contents;
                }
                presentStimuli();
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
    };


    presentStimuli = function() {
        // update the trial number label
        trial = trial + 1;
        $("#trial-number").html(trial);
        if (trial <= num_practice_trials) {
            $("#practice-trial").html("This is a practice trial");
        } else {
            $("#practice-trial").html("This is NOT a practice trial");
        }

        $("#instructions").html("Are there more blue or yellow dots?");

        // Show the participant the stimulus.
        if (learning_strategy === "asocial") {

            regenerateDisplay(state);

            $("#more-blue").addClass('disabled');
            $("#more-yellow").addClass('disabled');

            presentDisplay();

            $("#stimulus-stage").show();
            $("#response-form").hide();
            $("#more-yellow").show();
            $("#more-blue").show();
        }

        // Show the participant the hint.
        if (learning_strategy == "social") {

            document.getElementById("see_dots_div").style.visibility = "visible";

            if (meme == "blue" | meme == "yellow") {
                $("#stimulus_div").html("<br><br><br><br>Someone in the previous batch decided:<br><font color='#428bca'><b>BLUE</b></font>");
            } else {
                if (meme == "yellow") {
                    $("#stimulus_div").html("<br><br><br><br>Someone in the previous batch decided:<br><font color='#FBB829'><b>YELLOW</b></font>");
                } else {
                    meme = JSON.parse(meme);
                    if (meme.blue === undefined) {
                        $("#stimulus_div").html("<br><br>Three batches ago:<br><b><font color='#428bca'>" +
                          add_people_to_text(meme.blue3) + " decided BLUE</font></b> and <b><font color='#FBB829'>" +
                          add_people_to_text(meme.yellow3) + " decided YELLOW</font></b><br><br>" +
                          "Two batches ago:<br><b><font color='#428bca'>" +
                          add_people_to_text(meme.blue2) + " decided BLUE</font></b> and <b><font color='#FBB829'>" +
                          add_people_to_text(meme.yellow2) + " decided YELLOW</font></b><br><br>" +
                          "One batch ago:<br><b><font color='#428bca'>" +
                          add_people_to_text(meme.blue1) + " decided BLUE</font></b> and <b><font color='#FBB829'>" +
                          add_people_to_text(meme.yellow1) + " decided YELLOW</font></b>");
                    } else {
                        $("#stimulus_div").html("<br><br><br><br>In the previous batch:<br><b><font color='#428bca'>" +
                          add_people_to_text(meme.blue) + " decided BLUE</b></font> and <b><font color='#FBB829'>" +
                          add_people_to_text(meme.yellow) + " decided YELLOW</b></font>");
                    }
                }
            }
            lock = false;
        }
    };

    createAgent();

    function add_people_to_text(number) {
        if (number == 1) {
            return "" + number + " person";
        } else {
            return "" + number + " people";
        }
    }

    function presentDisplay (argument) {
        for (var i = dots.length - 1; i >= 0; i--) {
            dots[i].show();
        }
        setTimeout(function() {
            for (var i = dots.length - 1; i >= 0; i--) {
                dots[i].hide();
            }
            $("#more-blue").removeClass('disabled');
            $("#more-yellow").removeClass('disabled');
            lock = false;
            paper.clear();
        }, 1000);

    }

    function regenerateDisplay (state) {

        // Display parameters
        width = 600;
        height = 400;
        numDots = 80;
        dots = [];
        blueDots = Math.round(state * numDots);
        yellowDots = numDots - blueDots;
        sizes = [];
        rMin = 10; // The dots' minimum radius.
        rMax = 20;
        horizontalOffset = (window.innerWidth - width) / 2;

        paper = Raphael(horizontalOffset, 200, width, height);

        colors = [];
        colorsRGB = ["#428bca", "#FBB829"];

        for (var i = blueDots - 1; i >= 0; i--) {
            colors.push(0);
        }

        for (var i = yellowDots - 1; i >= 0; i--) {
            colors.push(1);
        }

        colors = shuffle(colors);

        while (dots.length < numDots) {

            // Pick a random location for a new dot.
            r = randi(rMin, rMax);
            x = randi(r, width - r);
            y = randi(r, height - r);

            // Check if there is overlap with any other dots
            pass = true;
            for (var i = dots.length - 1; i >= 0; i--) {
                distance = Math.sqrt(Math.pow(dots[i].attrs.cx - x, 2) + Math.pow(dots[i].attrs.cy - y, 2));
                if (distance < (sizes[i] + r)) {
                    pass = false;
                }
            }

            if (pass) {
                var dot = paper.circle(x, y, r);
                dot.hide();
                // use the appropriate color.
                dot.attr("fill", colorsRGB[colors[dots.length]]); // FBB829
                dot.attr("stroke", "#fff");
                dots.push(dot);
                sizes.push(r);
            }
        }
    }

    function randi(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function shuffle(o){
        for(var j, x, i = o.length; i; j = Math.floor(Math.random() * i), x = o[--i], o[i] = o[j], o[j] = x);
        return o;
    }

    // $("#finish-reading").click(function() {
    //  $("#stimulus-stage").hide();
    //  $("#response-form").show();
    //  $("#submit-response").removeClass('disabled');
    // });

    reportBlue = function () {
        document.getElementById("see_dots_div").style.visibility = "hidden";
        if(lock === false) {
            lock = true;
            $("#more-blue").addClass('disabled');
            $("#more-blue").html('Sending...');
            $("#reproduction").val("");
            $("#stimulus_div").html("");

            reqwest({
                url: "/info/" + my_node_id,
                method: 'post',
                data: {
                    contents: "blue",
                    info_type: "Meme"
                },
                success: function (resp) {
                    $("#more-blue").removeClass('disabled');
                    $("#more-blue").blur();
                    $("#more-blue").html('Blue');
                    createAgent();
                }
            });
        }
    };

    reportYellow = function () {
        document.getElementById("see_dots_div").style.visibility = "hidden";
        if(lock === false) {
            lock = true;
            $("#more-yellow").addClass('disabled');
            $("#more-yellow").html('Sending...');
            $("#reproduction").val("");
            $("#stimulus_div").html("");

            reqwest({
                url: "/info/" + my_node_id,
                method: 'post',
                data: {
                    contents: "yellow",
                    info_type: "Meme"
                },
                success: function (resp) {
                    $("#more-yellow").removeClass('disabled');
                    $("#more-yellow").blur();
                    $("#more-yellow").html('Yellow');
                    createAgent();
                }
            });
        }
    };

    $(document).keydown(function(e) {
        var code = e.keyCode || e.which;
        if(code == 70) { //Enter keycode
            reportBlue();
        } else if (code == 74) {
            reportYellow();
        }
    });

    $("#more-yellow").click(function() {
        reportYellow();
    });

    $("#more-blue").click(function() {
        reportBlue();
    });

    $("#see_dots_button").click(function() {
        reqwest({
            url: "/saw_the_dots",
            method: 'post',
            data: {
                participant_id: uniqueId,
                node_id: my_node_id,
            },
            success: function (resp) {
                document.getElementById("see_dots_div").style.visibility = "hidden";
                old_html = $("#stimulus_div").html();
                $("#stimulus_div").html("");
                regenerateDisplay(state);
                presentDisplay();
                setTimeout(function() {
                    $("#stimulus_div").html(old_html);
                }, 1050);
            },
            error: function (err) {
                console.log(err);
                err_response = JSON.parse(err.response);
                $('body').html(err_response.html);
            }
        });
        
    });
};

/****************
* Questionnaire *
****************/

var Questionnaire = function() {

    var error_message = "<h1>Oops!</h1><p>Something went wrong submitting your HIT. This might happen if you lose your internet connection. Press the button to resubmit.</p><button id='resubmit'>Resubmit</button>";

    record_responses = function() {

        psiTurk.recordTrialData({'phase':'postquestionnaire', 'status':'submit'});

        $('textarea').each( function(i, val) {
            psiTurk.recordUnstructuredData(this.id, this.value);
        });
        $('select').each( function(i, val) {
            psiTurk.recordUnstructuredData(this.id, this.value);
        });

    };

    prompt_resubmit = function() {
        replaceBody(error_message);
        $("#resubmit").click(resubmit);
    };

    resubmit = function() {
        replaceBody("<h1>Trying to resubmit...</h1>");
        reprompt = setTimeout(prompt_resubmit, 10000);

        psiTurk.saveData({
            success: function() {
                clearInterval(reprompt);
                psiTurk.computeBonus('compute_bonus', function(){finish()});
            },
            error: prompt_resubmit
        });
    };

    // Load the questionnaire snippet
    psiTurk.showPage('postquestionnaire.html');
    psiTurk.recordTrialData({'phase':'postquestionnaire', 'status':'begin'});

    $("#next").click(function () {
        $('#next').prop('disabled', true);
        $("#next-symbol").attr('class', 'glyphicon glyphicon-refresh glyphicon-refresh-animate');
        record_responses();
        psiTurk.saveData({
            success: function(){
                psiTurk.completeHIT();
            },
            error: prompt_resubmit});
    });


};

// Task object to keep track of the current phase
var currentview;

/*******************
 * Run Task
 ******************/
$(window).load( function(){
    psiTurk.doInstructions(
        instructionPages, // a list of pages you want to display in sequence
        function() { currentview = new StroopExperiment(); } // what you want to do when you are done with instructions
    );
});
